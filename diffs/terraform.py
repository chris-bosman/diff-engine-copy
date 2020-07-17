import json

from distutils.util import strtobool
from db import mongo

def generate_diffs(bucket, key):
    resource_types = mongo.infra_db.list_collection_names()
    message = ""
    drift_count = 0
    
    for type in resource_types:
        meta_collection = mongo.meta_db[f"{type}-{bucket}/{key}"]
        tf_collection = mongo.svc_db[f"{bucket}/{key}"]
        infra_collection = mongo.infra_db[type]

        message += f"""
        ################################
        Evaluating {type} objects...
        ################################
        """
        resources = meta_collection.find_one({})

        if len(resources['diff_ids']) > 0:
            with open(f"diffs/field_translations/aws_tf/{type}.json", "r") as f:
                field_translation_file = json.load(f)
            for resource_id in resources['diff_ids']:
                svc_doc = tf_collection.find_one({ 'aws_id': resource_id })
                infra_doc = [ doc for doc in infra_collection.find() if resource_id in doc.values() ][0]
                message += f"\nEvaluating {svc_doc['terraform_name']}...\n"

                post_parse_msg, post_parse_drift_count = parse_fields(field_translation_file, svc_doc, infra_doc)

                drift_count = post_parse_drift_count + drift_count

                if post_parse_drift_count > 0:
                    message += post_parse_msg

    if drift_count == 0:
        message += f"\n\tNo drift has been detected on {svc_doc['terraform_name']}.\n"

    return message

def parse_fields(translation_file, svc_doc, infra_doc):
    message = ""
    drift_count = 0

    for svc_attr, infra_attr in translation_file.items():
        if svc_attr != "tags":
            if svc_doc[svc_attr] in ["true", "false"] and bool(strtobool(svc_doc[svc_attr])) == infra_doc[infra_attr]:
                pass
            elif svc_doc[svc_attr] == infra_doc[infra_attr]:
                pass
            else:
                message += f"\n\tYour code indicates that {infra_attr} should be {svc_doc[svc_attr]}, but instead it is {infra_doc[infra_attr]}.\n"
                drift_count += 1
        else:
            tag_message, tag_drift_count = generate_tag_diffs(svc_doc, infra_doc)
            drift_count = drift_count + tag_drift_count
            if tag_drift_count > 0:
                message += tag_message

    return message, drift_count

def generate_vpc_diffs(bucket, key):
    meta_collection = mongo.meta_db[f"aws_vpcs-{bucket}/{key}"]
    tf_collection = mongo.svc_db[f"{bucket}/{key}"]
    infra_collection = mongo.infra_db["aws_vpc"]
    vpcs = meta_collection.find_one({})

    for vpc in vpcs['diff_vpc_ids']:
        svc_doc = tf_collection.find_one({ 'aws_id': vpc })
        infra_doc = infra_collection.find_one({ 'VpcId': vpc })
        with open(f"diffs/field_translations/aws_tf/vpcs.json", "r") as f:
            field_translation_file = json.load(f)

        message = f"\nEvaluating VPC {svc_doc['terraform_name']}...\n"
        drift_count = 0
        for svc_attr, infra_attr in field_translation_file.items():
            if svc_attr != "tags":
                if svc_doc[svc_attr] in ["true", "false"] and bool(strtobool(svc_doc[svc_attr]) == infra_doc[infra_attr]) :
                    pass
                elif svc_doc[svc_attr] == infra_doc[infra_attr]:
                    pass
                else:
                    message += f"\tYour code indicates that {infra_attr} should be {svc_doc[svc_attr]}, but instead it is {infra_doc[infra_attr]}.\n"
                    drift_count += 1
            else:
                tag_message, tag_drift_count = generate_tag_diffs(svc_doc, infra_doc)
                drift_count = drift_count + tag_drift_count
                if tag_drift_count > 0:
                    message += tag_message

        if drift_count == 0:
            message += f"\tNo drift has been detected on {svc_doc['terraform_name']}.\n"

        return message

def generate_tag_diffs(svc_doc, infra_doc):
    message = ""
    drift_count = 0

    tag_count = int(svc_doc["tags.%"])
    if tag_count != len(infra_doc["Tags"]):
        message += f"\tYour code indicates that there should be {tag_count} tags, but there are {len(infra_doc['Tags'])} tags defined.\n"
        drift_count += 1

    svc_tag_keys = [ attr.split(".")[1] for attr in svc_doc.keys() if "tags." in attr and attr != "tags.%" ]
    infra_tag_keys = [ tag['Key'] for tag in infra_doc['Tags'] ]
    matched_keys = set(svc_tag_keys).intersection(infra_tag_keys)

    if len(matched_keys) < len(infra_tag_keys):
        for svc_key in svc_tag_keys:
            if svc_key not in infra_tag_keys:
                message += f"\tYour code indicates that there should be a tag with tye key {svc_key}, but it does not exist on the resource.\n"
                drift_count += 1

        for infra_key in infra_tag_keys:
            if infra_key not in svc_tag_keys:
                message += f"\tThere is a tag on this resource with the key {infra_key} that is not defined in your code.\n"
                drift_count += 1

    for key in matched_keys:
        tag_count = len(infra_doc['Tags'])
        tag_index = tag_count - 1
        infra_value = [ item['Value'] for item in infra_doc['Tags'] if item['Key'] == key ]

        while tag_count > 0:
            svc_value = svc_doc[f"tags.{key}"]
            if svc_value not in infra_value:
                message += f"\tYour code indicates that the tag {key} should be {svc_value}, but the resource shows that tag's value is {infra_value[0]}.\n"
                drift_count += 1

            tag_count -= 1
    
    return message, drift_count