import logging, sys, os
from google.cloud import storage



logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


class StorageHandler:
    
    def __init__(self, bucket_name = os.getenv("DOCS_BUCKET"), region = os.getenv("GCP_REGION")):
        self.storage_client = storage.Client()
        self.bucket_name = bucket_name
        self.bucket = self.get_bucket(bucket_name, region=region)
        self.region = region


    def get_bucket(self, bucket_name: str, region: str) -> storage.Bucket:
        """Creates or return bucket"""
        
        ## If bucket initialized, return it
        if self.bucket:
            return self.bucket

        ## Check if bucket exists
        buckets = self.storage_client.list_buckets()
        for bucket in buckets:
            if bucket.name == bucket_name:
                logging.info(f"Bucket {bucket_name} already exists")
                self.bucket = bucket
                return self.bucket

        ## Create bucket if needed
        bucket = self.storage_client.bucket(bucket_name)
        bucket.storage_class = "STANDARD"
        
        new_bucket = self.storage_client.create_bucket(bucket, location=region)

        logging.info("Created bucket {} in {} with storage class {}".format(new_bucket.name, new_bucket.location, new_bucket.storage_class))
        return new_bucket

    def download_file(self, user_id, file_name, destination_folder) -> str:
        
        bucket = self.get_bucket(bucket_name)

        blob = bucket.blob(f"{user_id}/{file_name}")
        destination_file = f"{destination_folder}/{file_name}"
        blob.download_to_filename(destination_file)

        logging.info(f"File {file_name} downloaded to {destination_file}")
        return destination_file



    def upload_to_user_folder(self, user_id: str, file_path: str, name: str) -> None:

        ## Check if the file exists
        if not os.path.exists(file_path):
            logging.error(f"File {file_path} does not exist")
            return

        file_name = os.path.basename(file_path)
        blob = self.bucket.blob(f"{user_id}/{name}")
        blob.upload_from_filename(file_path) 

        logging.info(f"File {file_path} uploaded to {self.bucket_name}/{user_id}/{file_path}")




if __name__ == "__main__":
    bucket_name = "icog-dev-bucket-01"
    user_id = "user-01"
    file_path = "data/French_Revolution_Projects_Tasks.json"
    storage_handler = StorageHandler(bucket_name)
    storage_handler.upload_to_user_folder(bucket_name, user_id, file_path)
    #create_bucket("icog-dev-bucket-01")

