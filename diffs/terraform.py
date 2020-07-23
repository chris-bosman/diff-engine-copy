import json

from distutils.util import strtobool
from db import mongo
from pymongo import ReturnDocument

def generate_diffs(bucket, key):
    drift_doc = {}
    resource_types = mongo.infra_db.list_collection_names()

    for type in resource_types:
        meta_collection = mongo.meta_db[f"{type}-{bucket}/{key}"]
        tf_collection = mongo.svc_db[f"{bucket}/{key}"]
        infra_collection = mongo.infra_db[type]

        resources = meta_collection.find_one({})

        if len(resources['diff_ids']) > 0:
            with open(f"diffs/field_translations/aws_tf/{type}.json", "r") as f:
                field_translation_file = json.load(f)
            for resource_id in resources['diff_ids']:
                svc_doc = tf_collection.find_one({ 'aws_id': resource_id })
                infra_doc = [ doc for doc in infra_collection.find() if resource_id in doc.values() ][0]

                drift_doc = parse_fields(field_translation_file, svc_doc, infra_doc)
                drift_doc['resource_id'] = resource_id

                diff_coll = mongo.diff_db[f"{type}-{bucket}/{key}"]
                upload = diff_coll.find_one_and_replace(
                    {"resource_id": resource_id},
                    drift_doc,
                    return_document=ReturnDocument.AFTER,
                    upsert=True
                )

                drift_doc = {}

    return {
        "message": "Successfully generated diffs",
        "status": 200
    }

def parse_fields(translation_file, svc_doc, infra_doc):
    drift_doc = {"diffs": {}}

    for svc_attr, infra_attr_raw in translation_file.items():
        if isinstance(infra_attr_raw, dict):
            infra_attr = infra_attr_raw['parent']
        else:
            infra_attr = infra_attr_raw

        if svc_attr not in list(svc_doc.keys()):
            svc_doc[svc_attr] = ""

        if isinstance(infra_doc[infra_attr], list) == False:
            if svc_doc[svc_attr] in ["true", "false"] and bool(strtobool(svc_doc[svc_attr])) == infra_doc[infra_attr]:
                pass
            elif svc_doc[svc_attr] == "false" and infra_doc[infra_attr] in ("", (), [], {}, None):
                pass
            elif svc_doc[svc_attr] == infra_doc[infra_attr]:
                pass
            else:
                drift_doc['diffs'] = {
                    infra_attr: {
                        "svc_prop": svc_doc[svc_attr],
                        "infra_prop": infra_doc[infra_attr]
                    }
                }

        else:
            drift_doc = generate_list_diffs(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc, translation_file)

    return drift_doc

def generate_list_diffs(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc, translation_file):
    drift_doc = diff_list_count(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc)
    for attr in infra_doc[infra_attr]:
        if isinstance(attr, dict) == False:
            drift_doc = diff_flat_list(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc)
        elif infra_attr == "Tags":
            drift_doc = diff_tags(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc)
        else:
            drift_doc = diff_dicts(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc, translation_file)

    return drift_doc

def diff_list_count(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc):
    svc_count = len(svc_doc[svc_attr])
    infra_count = len(infra_doc[infra_attr])

    if svc_count != infra_count:
        drift_doc['diffs'][infra_attr] = {
            f"svc_{svc_attr}_count": svc_count
        }
        drift_doc['diffs'][infra_attr] = {
            f"infra_{svc_attr}_count": infra_count
        }

    return drift_doc

def diff_flat_list(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc):
    svc_list = svc_doc[svc_attr]
    infra_list = infra_doc[infra_attr]

    not_in_infra = list(set(svc_list) - set(infra_list))
    not_in_svc = list(set(infra_list) - set(svc_list))

    if len(not_in_infra) > 0:
        drift_doc['diffs'][infra_attr] = {
            "svc_diffs": not_in_infra
        }

    if len(not_in_svc) > 0:
        drift_doc['diffs'][infra_attr] = {
            "infra_diffs": not_in_svc
        }

    return drift_doc

def diff_tags(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc):
    infra_tags = infra_doc[infra_attr]
    svc_tags = svc_doc[svc_attr]

    infra_tag_keys = [ tag['Key'] for tag in infra_tags ]
    infra_tag_values = [ tag['Value'] for tag in infra_tags ]
    svc_tag_keys = list(svc_tags.keys())
    svc_tag_values = list(svc_tags.values())

    not_in_infra = list(set(svc_tag_keys) - set(infra_tag_keys))
    not_in_svc = list(set(infra_tag_keys) - set(svc_tag_keys))
    in_both = list(set(infra_tag_keys) & set(svc_tag_keys))

    in_both_dict = {}
    for key in in_both:
        if svc_tags[key] == [ tag['Value'] for tag in infra_tags if tag['Key'] == key ][0]:
            pass
        else:
            in_both_dict[key] = {
                "svc_value": svc_tags[key],
                "infra_value": [ tag['Value'] for tag in infra_tags if tag['Key'] == key ][0]
            }

    if len(in_both_dict) > 0:
        drift_doc['diffs'][infra_attr] = in_both_dict

    if len(not_in_infra) > 0:
            drift_doc['diffs'][infra_attr] = {
                "svc_diffs": { k:v for (k,v) in tag.items() if bool(set(list(tag.values())) & set(not_in_infra))}
            }

    if len(not_in_svc) > 0:
        for tag in infra_tags:
            drift_doc['diffs'][infra_attr] = {
                "infra_diffs": { k:v for (k,v) in tag.items() if bool(set(list(tag.values())) & set(not_in_svc))}
            }

    return drift_doc

def diff_dicts(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc, translation_file):
    infra_attr_name = translation_file[svc_attr]["parent"]

    svc_map_value_set = set(map(tuple, svc_doc[svc_attr]))
    infra_map_value_set = set(map(tuple, infra_doc[infra_attr]))
    differing_values = list(svc_map_value_set ^ infra_map_value_set)
    svc_diff_objects = []
    infra_diff_objects = []

    for diffs in differing_values:
        diff_objects = [ item for item in svc_doc[svc_attr] if list(item.values()) in list(diffs) ]
        if len(diff_objects) > 0:
            svc_diff_object = diff_objects[0]
            svc_diff_objects.append(svc_diff_object)

        diff_objects = [ item for item in infra_doc[infra_attr_name] if list(item.values()) in list(diffs) ]
        if len(diff_objects) > 0:
            infra_diff_object = diff_objects[0]
            infra_diff_objects.append(infra_diff_object)

    if len(svc_diff_objects) > 0:
        drift_doc['diffs'][infra_attr_name] = {
            "svc_diffs": []
        }
        drift_doc['diffs'][infra_attr_name]["svc_diffs"].append(svc_diff_objects)

    if len(infra_diff_objects) > 0:
        drift_doc['diffs'][infra_attr_name] = {
            "infra_diffs": []
        }
        drift_doc['diffs'][infra_attr_name]["infra_diffs"].append(infra_diff_objects)

    return drift_doc