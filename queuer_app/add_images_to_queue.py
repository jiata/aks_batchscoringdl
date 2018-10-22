from azure.servicebus import ServiceBusService, Message, Queue
from azure.storage.blob import BlockBlobService
import os
import argparse


def create_service_bus_client():
    return ServiceBusService(
        service_namespace=os.getenv("SB_NAMESPACE"),
        shared_access_key_name=os.getenv("SB_SHARED_ACCESS_KEY_NAME"),
        shared_access_key_value=os.getenv("SB_SHARED_ACCESS_KEY_VALUE"),
    )


def create_storage_client():
    return BlockBlobService(
        account_name=os.getenv("STORAGE_ACCOUNT_NAME"),
        account_key=os.getenv("STORAGE_ACCOUNT_KEY"),
    )


if __name__ == "__main__":
    """
    This script will take the names of all images inside of a directory in a 
    container in Azure storage and add the name of the images as messages to 
    the Service Bus queue.
    """

    parser = argparse.ArgumentParser(
        description="Add messages to queue based on images in blob storage."
    )
    parser.add_argument(
        "--blob-dir",
        dest="blob_dir",
        help="The name of the image directory in your Azure storage container",
        default="input",
    )
    parser.add_argument(
        "--queue-limit",
        dest="queue_limit",
        help="The maximum number of items to add to the queue.",
        type=int,
        default=None,
    )
    args = parser.parse_args()
    blob_dir = args.blob_dir
    queue_limit = args.queue_limit

    # service bus creds
    bus_service = create_service_bus_client()

    # blob creds
    block_blob_service = create_storage_client()

    # list all images in specified blob under directory 'blob_dir'
    blob_iterator = block_blob_service.list_blobs(
        os.getenv("STORAGE_CONTAINER_NAME"), 
        prefix=blob_dir
    )

    # for all images found, add to queue
    print(
        "Adding {} images in the directory '{}' of the storage container '{}' to the queue '{}'.".format(
            queue_limit if queue_limit is not None else "all",
            blob_dir, 
            os.getenv("STORAGE_CONTAINER_NAME"),
            os.getenv("SB_QUEUE")
        )
    )
    for i, blob in enumerate(blob_iterator):
        
        if queue_limit is not None and i >= queue_limit:
            print("Queue limit is reached. Exiting process...")
            exit(0)
            
        print("adding {} to queue...".format(blob.name.split("/")[-1]))
        msg = Message(blob.name.encode())
        bus_service.send_queue_message(os.getenv("SB_QUEUE"), msg)
