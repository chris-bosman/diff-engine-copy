import dotenv
import os
dotenv.load_dotenv()
bucket = os.getenv('AWS_S3_BUCKET')
path = os.getenv('AWS_S3_PATH')
from readers import terraform as tf
tf.store_tfstate_s3(bucket, path)