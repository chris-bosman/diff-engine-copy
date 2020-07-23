import boto3
import json
import os
import re

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
        attributes = handle_complex_attributes(attributes)
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

def handle_complex_attributes(attributes):
    complex_attributes = list(dict.fromkeys([ attr.split('.')[0] for attr in attributes if "." in attr ]))
    for attr in complex_attributes:
        attributes[attr] = []

        attr_key_list = [ field for field in attributes if re.match(re.compile(f"^{attr}\.[0-9]{{1,}}$"), field) ]
        attr_fields = [ field for field in attributes if f"{attr}." in field and field not in attr_key_list and "#" not in field and "%" not in field ]
        attr_groups = list(set([ field.split('.')[1] for field in attr_fields if "tags" not in field ]))

        if attr == "tags":
            attributes = complex_attribute_tag_helper(attr, attr_fields, attributes)

        if attr_key_list:
            attributes = complex_attribute_list_helper(attr, attr_key_list, attributes)

        if attr_groups:
            attributes = complex_attribute_dict_helper(attr, attr_fields, attr_groups, attributes)
                            
    return attributes

def complex_attribute_list_helper(attr, attr_key_list, attributes):
    attributes[attr] = [ attributes[key] for key in attr_key_list ]

    return attributes

def complex_attribute_tag_helper(attr, attr_fields, attributes):
    attributes[attr] = {}

    for field in attr_fields:
        key = field.split(".")[1]
        attributes[attr][key] = attributes[field]

    return attributes

def complex_attribute_dict_helper(attr, attr_fields, attr_groups, attributes):
    for group in attr_groups:
        group_object = {}
        map_attrs = [ field for field in attr_fields if f"{attr}.{group}." in field ]
        for item in map_attrs:
            if re.match(re.compile('^(.+)[a-z]{1}$'), item):
                if len(item.split('.')) == 3:
                    group_object[item.split('.')[2]] = attributes[item]
                elif len(item.split('.')) == 5:
                    group_object[item.split('.')[2]] = {}
                    group_object[item.split('.')[2]][item.split('.')[4]] = attributes[item]
            elif re.match(re.compile('^(.+)\.[0-9]{1,}'), item):
                if len(item.split('.')) == 4:
                    group_object[item.split('.')[2]] = []
                    group_object[item.split('.')[2]].append(attributes[item])
                if len(item.split('.')) == 6:
                    group_object[item.split('.')[2]] = {}
                    group_object[item.split('.')[2]][item.split('.')[4]] = []
                    group_object[item.split('.')[2]][item.split('.')[4]].append(attributes[item])
        attributes[attr].append(group_object)

    return attributes