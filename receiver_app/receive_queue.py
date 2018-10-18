from azure.servicebus import ServiceBusService, Message, Queue
from azure.storage.blob import BlockBlobService
import style_transfer
import pathlib
import datetime
import time
import os
import logging
from logging.handlers import RotatingFileHandler
import sys

# make .tmp dir and input/output folders in it
pathlib.Path(".tmp/input").mkdir(parents=True, exist_ok=True)
pathlib.Path(".tmp/output").mkdir(parents=True, exist_ok=True)
pathlib.Path(".tmp/log").mkdir(parents=True, exist_ok=True)

# declare some variables
now = datetime.datetime.now()
az_blob_container_name = "aks"
az_input_folder = "input"
az_output_folder = "output_{}".format(now.strftime("%Y%m%d_%H%M%S"))
az_log_folder = "log_{}".format(now.strftime("%Y%m%d_%H%M%S"))
local_input_folder = "input"
local_output_folder = "output"
local_log_folder = "log"

# set up logger
handler_format = logging.Formatter(
    "%(asctime)s [%(name)s:%(filename)s:%(lineno)s] %(levelname)s - %(message)s"
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(handler_format)
logger = logging.getLogger("root")
logger.setLevel(logging.DEBUG)
logger.addHandler(console_handler)
logger.propagate = False

# service bus creds
bus_service = ServiceBusService(
    service_namespace=os.getenv("SB_SERVICE_NAMESPACE"),
    shared_access_key_name=os.getenv("SB_SHARED_ACCESS_KEY_NAME"),
    shared_access_key_value=os.getenv("SB_SHARED_ACCESS_KEY_VALUE"),
)

# blob creds
block_blob_service = BlockBlobService(
    account_name=os.getenv("STORAGE_ACCOUNT_NAME"),
    account_key=os.getenv("STORAGE_ACCOUNT_KEY"),
)

# download style image to tmp
block_blob_service.get_blob_to_path(
    "aks", "style_image.jpg", os.path.join(".tmp", "style_image.jpg")
)

# start listening...
queue = os.getenv("SB_QUEUE")
logger.debug("start listening to queue {} on service bus...".format(queue))

while True:
    logger.debug("Peek queue...")
    msg = bus_service.receive_queue_message(queue, peek_lock=True, timeout=60)

    # if msg is none (probably means nothing in queue and the above line has timed out)
    if msg.body is None:
        logger.debug("Receiver has timed out, queue is empty. Exiting program...")
        exit(0)

    # else, write out and delete msg
    else:
        # get blob name from msg body
        blob_path = msg.body.decode("utf-8")
        blob_name = blob_path.split("/")[-1]

        # add style transfer logs to new file
        log_file = "{}.log".format(".".join(blob_name.split(".")[:-1]))
        file_handler = RotatingFileHandler(
            os.path.join(
                ".tmp/{}".format(local_log_folder),
                log_file
            ),
            maxBytes=20000,
        )
        file_handler.setFormatter(handler_format)
        logger.addHandler(file_handler)
        logger.debug("Queue message: '{}'".format(blob_path))

        # set input/output file vars
        local_input_file = ".tmp/{}/{}".format(local_input_folder, blob_name)
        local_output_file = ".tmp/{}/{}".format(local_output_folder, blob_name)
        local_log_file = ".tmp/{}/{}".format(local_log_folder, log_file)

        # put blob in temp dir
        block_blob_service.get_blob_to_path(
            az_blob_container_name,
            "{}/{}".format(az_input_folder, blob_name),
            local_input_file,
        )

        # run style transfer
        logger.debug("Starting style transfer on {}".format(blob_name))
        style_transfer.run(
            style_image=".tmp/style_image.jpg",
            content_image_dir=".tmp/{}".format(local_input_folder),
            content_image_list=blob_name,
            output_image_dir=".tmp/{}".format(local_output_folder),
            style_weight=10 ** 8,
            content_weight=1,
            num_steps=300,
            image_size=512
        )
        logger.debug("Finished style transfer on {}".format(blob_name))

        # upload output + log file
        block_blob_service.create_blob_from_path(
            az_blob_container_name,
            "{}/{}".format(az_output_folder, blob_name),
            local_output_file,
        )
        block_blob_service.create_blob_from_path(
            az_blob_container_name,
            "{}/{}".format(az_log_folder, log_file),
            local_log_file,
        )
        logger.debug("Uploaded output file and log file to storage")

        # delete tmp
        if os.path.exists(local_input_file):
            os.remove(local_input_file)
        if os.path.exists(local_output_file):
            os.remove(local_output_file)

        # delete msg
        logger.debug("Deleting queue message...")
        msg.delete()

        # pop logger handler
        logger.handlers.pop()
