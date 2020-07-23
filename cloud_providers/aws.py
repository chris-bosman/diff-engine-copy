import boto3
import json
import os

from db import mongo
from pymongo import ReturnDocument

def supplement_aws_vpc_data(vpc, client):
    classic_link = client.describe_vpc_classic_link(VpcIds=[vpc['VpcId']])
    classic_link_dns = client.describe_vpc_classic_link_dns_support(VpcIds=[vpc['VpcId']])
    dns_support = client.describe_vpc_attribute(Attribute='enableDnsSupport', VpcId=vpc['VpcId'])
    dns_hostnames = client.describe_vpc_attribute(Attribute='enableDnsHostnames', VpcId=vpc['VpcId'])
    enable_classiclink = classic_link['Vpcs'][0]['ClassicLinkEnabled']
    enable_classiclink_dns_support = classic_link_dns['Vpcs'][0]['ClassicLinkDnsSupported']
    enable_dns_support = dns_support['EnableDnsSupport']['Value']
    enable_dns_hostnames = dns_hostnames['EnableDnsHostnames']['Value']

    supplemental_vpc_data = {
        "EnableClassicLink": enable_classiclink,
        "EnableClassicLinkDnsSupport": enable_classiclink_dns_support,
        "EnableDnsSupport": enable_dns_support,
        "EnableDnsHostnames": enable_dns_hostnames
    }

    for field in supplemental_vpc_data.keys():
        vpc[field] = supplemental_vpc_data[field]

    if "Ipv6CidrBlockAssociationSet" in vpc.keys():
        if vpc["Ipv6CidrBlockAssociationSet"][0]["Ipv6CidrBlockState"]["State"] == "associated":
            vpc["AssignIpv6Block"] = True
    else:
        vpc["AssignIpv6Block"] = False

    return vpc

def supplement_aws_subnet_data(subnet, client):
    if subnet["Ipv6CidrBlockAssociationSet"] == []:
        subnet["Ipv6CidrBlock"] = ""
    else:
        subnet["Ipv6CidrBlock"] = subnet["Ipv6CidrBlockAssociationSet"][0]["Ipv6CidrBlock"]

    if "OutpostArn" not in subnet.keys():
        subnet["OutpostArn"] = ""
    
    return subnet

def supplement_aws_lb_data(lb, client):
    attributes = client.describe_load_balancer_attributes(LoadBalancerArn=lb['LoadBalancerArn'])['Attributes']
    tags = [ tag_descriptions['Tags'] for tag_descriptions in client.describe_tags(ResourceArns=[lb['LoadBalancerArn']])['TagDescriptions'] if tag_descriptions['ResourceArn'] == lb['LoadBalancerArn'] ][0]

    lb['Tags'] = tags

    lb['EnableDeletionProtection'] = [ attr['Value'] for attr in attributes if "deletion_protection.enabled"  in attr.values() and attr['Key'] == "deletion_protection.enabled" ]

    if len(lb["EnableDeletionProtection"]) == 1:
        lb["EnableDeletionProtection"] = lb["EnableDeletionProtection"][0]
    elif lb["EnableDeletionProtection"] == []:
        lb["EnableDeletionProtection"] = ""

    lb['AccessLogs'] = [{
        "Bucket": [ attr['Value'] for attr in attributes if "access_logs.s3.bucket" in attr.values() and attr['Key'] == "access_logs.s3.bucket" ][0],
        "Enabled": [ attr['Value'] for attr in attributes if "access_logs.s3.enabled" in attr.values() and attr['Key'] == "access_logs.s3.enabled" ][0],
        "Prefix": [ attr['Value'] for attr in attributes if "access_logs.s3.prefix"in attr.values() and attr['Key'] == "access_logs.s3.prefix" ][0]
    }]
    lb['Subnets'] = [ az_attr['SubnetId'] for az_attr in lb['AvailabilityZones'] ]
    lb['SubnetMapping'] = []


    for az_attr in lb['AvailabilityZones']:
        subnet_mapping_object = {}
        subnet_mapping_object['SubnetId'] = az_attr['SubnetId']
        if len(az_attr['LoadBalancerAddresses']) > 0 and az_attr['LoadBalancerAddresses'][0]['AllocationId']:
            subnet_mapping_object['AllocationId'] = az_attr['LoadBalancerAddresses'][0]['AllocationId']
        else:
            subnet_mapping_object['AllocationId'] = ""

        lb['SubnetMapping'].append(subnet_mapping_object)

    if "SecurityGroups" not in list(lb.keys()):
        lb["SecurityGroups"] = []

    if lb["Scheme"] == "internet-facing":
        lb["Scheme"] = False
    else:
        lb["Scheme"] = True

    return lb

def supplement_aws_alb_data(lb, client):
    if lb['Type'] == "application":
        lb = supplement_aws_lb_data(lb, client)

        attributes = client.describe_load_balancer_attributes(LoadBalancerArn=lb['LoadBalancerArn'])['Attributes']
        lb['IdleTimeout'] = [ attr['Value'] for attr in attributes if 'idle_timeout.timeout_seconds' in attr.values() and attr['Key'] == "idle_timeout.timeout_seconds" ]
        lb['DropInvalidHeaderFields'] = [ attr['Value'] for attr in attributes if 'routing.http.drop_invalid_header_fields.enabled' in attr.values() and attr['Key'] == 'routing.http.drop_invalid_header_fields.enabled' ]
        lb['EnableHttp2'] = [ attr['Value'] for attr in attributes if "routing.http2.enabled" in attr.values() and attr['Key'] == "routing.http2.enabled" ]
        
        fields = [
            "IdleTimeout",
            "DropInvalidHeaderFields",
            "EnableHttp2"
        ]

        for field in fields:
            if len(lb[field]) == 1:
                lb[field] = lb[field][0]
            elif lb[field] == []:
                lb[field] = ""

        return lb
    else:
        return None

def supplement_aws_nlb_data(lb, client):
    if lb['Type'] == "network":
        lb = supplement_aws_lb_data(lb, client)

        attributes = client.describe_load_balancer_attributes(LoadBalancerArn=lb['LoadBalancerArn'])['Attributes']
        lb['EnableCrossZoneLoadBalancing'] = [ attr['Value'] for attr in attributes if "load_balancing.cross_zone.enabled" in attr.values() and attr['Key'] == "load_balancing.cross_zone.enabled" ]

        if len(lb['EnableCrossZoneLoadBalancing']) == 1:
            lb['EnableCrossZoneLoadBalancing'] = lb['EnableCrossZoneLoadBalancing'][0]
        elif lb['EnableCrossZoneLoadBalancing'] == []:
            lb['EnableCrossZoneLoadBalancing'] = ""

        return lb
    else:
        return None

def generate_filter(resource_type):
    client = boto3.client(resource_type['filter']['client'], region_name=os.getenv('AWS_REGION'))
    filter_resources = getattr(client, resource_type['filter']['function'])()[resource_type['filter']['top_level']]
    filter_values = [ resource[resource_type['filter']['id_field']] for resource in filter_resources ]

    return filter_values


def store_resources():
    with open("cloud_providers/function_helpers/aws.json", "r") as f:
        helper_file = json.load(f)

    resource_list = list(helper_file.keys())
    for resource_type in resource_list:
        client = boto3.client(helper_file[resource_type]['client'], region_name=os.getenv('AWS_REGION'))
        if "filter" in list(helper_file[resource_type].keys()):
            filter_values = generate_filter(helper_file[resource_type])
            if helper_file[resource_type]['filter']['iterable']:
                resources = handle_iterable_resources(filter_values, helper_file, resource_type, client)
            else:
                filter = helper_file[resource_type]['filter']['field']
                resources = getattr(client, helper_file[resource_type]['function_name'])(filter=filter_values)[helper_file[resource_type]['top_level']]
        else:
            resources = getattr(client, helper_file[resource_type]["function_name"])()[helper_file[resource_type]['top_level']]
        collection = mongo.infra_db[resource_type]

        for resource in resources:
            resource = globals()[f"supplement_{resource_type}_data"](resource, client)

            if resource:
                collection.find_one_and_replace(
                    {helper_file[resource_type]['id_field']: resource[helper_file[resource_type]['id_field']]},
                    resource,
                    return_document=ReturnDocument.AFTER,
                    upsert=True
                )

    return {
        "message": "Success",
        "status": 200
    }

def handle_iterable_resources(filter_list, helper_file, resource_type, client):
    resources = []
    for value in filter_list:
        filter = { helper_file[resource_type]['filter']['field']: value }
        interim_result = getattr(client, helper_file[resource_type]['function_name'])(**filter)[helper_file[resource_type]['top_level']]
        resources = [ result for result in interim_result ]

    return resources