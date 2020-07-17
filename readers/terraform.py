import boto3
import json
import os

from db import mongo
from pymongo import ReturnDocument

def store_tfstate_s3(bucket, key):
    client = boto3.client('s3', region_name=os.getenv('AWS_REGION'))
    resp = client.get_object(
        Bucket=bucket,
        Key=key
    )

    state_file = json.loads(resp['Body'].read())
    resources = state_file['modules'][0]['resources']
    top_level_resources = resources.keys()

    tf_collection = mongo.svc_db[f"{bucket}/{key}"]
    for resource in top_level_resources:
        attributes = resources[resource]['primary']['attributes']
        attributes['aws_id'] = resources[resource]['primary']['id']
        attributes["terraform_name"] = resource
        attributes["terraform_type"] = resources[resource]['type']
        attributes["depends_on"] = resources[resource]['depends_on']
        upload = tf_collection.find_one_and_replace(
            {"aws_id": resources[resource]['primary']['id']},
            attributes,
            return_document=ReturnDocument.AFTER,
            upsert=True
        )

    return {
        "message": "Successfully uploaded Terraform State",
        "status": 200
    }