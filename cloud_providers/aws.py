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

    lb['DropInvalidHeaderFields'] = [ attr['Value'] for attr in attributes if 'routing.http.drop_invalid_header_fields.enabled' in attr.values() and attr['Key'] == 'routing.http.drop_invalid_header_fields.enabled' ]
    lb['IdleTimeout'] = [ attr['Value'] for attr in attributes if 'idle_timeout_seconds' in attr.values() and attr['Key'] == "idle_timeout.timeout_seconds" ]
    lb['EnableDeletionProtection'] = [ attr['Value'] for attr in attributes if "deletion_protection.enabled"  in attr.values() and attr['Key'] == "deletion_protection.enabled" ]
    lb['EnableCrossZoneLoadBalancing'] = [ attr['Value'] for attr in attributes if "load_balancing.cross_zone.enabled" in attr.values() and attr['Key'] == "load_balancing.cross_zone.enabled" ]
    lb['EnableHttp2'] = [ attr['Value'] for attr in attributes if "routing.http2.enabled" in attr.values() and attr['Key'] == "routing.http2.enabled" ]
    lb['AccessLogs'] = {
        "Bucket": [ attr['Value'] for attr in attributes if "access_logs.s3.bucket" in attr.values() and attr['Key'] == "access_logs.s3.bucket" ],
        "Enabled": [ attr['Value'] for attr in attributes if "access_logs.s3.enabled" in attr.values() and attr['Key'] == "access_logs.s3.enabled" ],
        "Prefix": [ attr['Value'] for attr in attributes if "access_logs.s3.prefix"in attr.values() and attr['Key'] == "access_logs.s3.prefix" ]
    }
    lb['Subnets'] = [ az_attr['SubnetId'] for az_attr in lb['AvailabilityZones'] ]
    lb['SubnetMapping'] = [ az_attr['LoadBalancerAddresses'] for az_attr in lb['AvailabilityZones'] ]

    for attr in lb:
        if attr == None or attr == []:
            attr = ""
        if len(attr) == 1:
            attr = attr[0]

    return lb

def supplement_aws_alb_data(lb, client):
    if lb['Type'] == "application":
        lb = supplement_aws_lb_data(lb, client)
        return lb
    else:
        return None

def supplement_aws_nlb_data(lb, client):
    if lb['Type'] == "network":
        lb = supplement_aws_lb_data(lb, client)
        return lb
    else:
        return None

def store_resources():
    with open("cloud_providers/function_helpers/aws.json", "r") as f:
        helper_file = json.load(f)

    resource_list = list(helper_file.keys())
    for resource_type in resource_list:
        client = boto3.client(helper_file[resource_type]['client'], region_name=os.getenv('AWS_REGION'))
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