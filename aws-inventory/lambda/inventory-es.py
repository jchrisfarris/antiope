# Copyright 2019-2020 Turner Broadcasting Inc. / WarnerMedia
# Copyright 2022 Chris Farris <chrisf@primeharbor.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import boto3
from botocore.exceptions import ClientError
import json
import os
import time
from datetime import datetime, timezone
from dateutil import tz
from time import sleep

from antiope.aws_account import *
from common import *

import logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, os.getenv('LOG_LEVEL', default='INFO')))
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

RESOURCE_PATH = "es/domain"
RESOURCE_TYPE = "AWS::Elasticsearch::Domain"

# AWS re-branded their managed ElasticSearch service to Amazon OpenSearch Service in 2021. As part of that
# they deprecated several ES specific API calls as documented here:
# https://docs.aws.amazon.com/opensearch-service/latest/developerguide/configuration-api.html

# For the purposes of data backwards compatibility, we will not change the RESOURCE_PATH or RESOURCE_TYPE for
# OpenSearch, however this code has been updated to leverage the latest boto3 service and API calls


def lambda_handler(event, context):
    logger.debug("Received event: " + json.dumps(event, sort_keys=True))
    message = json.loads(event['Records'][0]['Sns']['Message'])
    logger.info("Received message: " + json.dumps(message, sort_keys=True))

    try:

        target_account = AWSAccount(message['account_id'])

        regions = target_account.get_regions()
        if 'region' in message:
            regions = [message['region']]

        # describe ES Domains
        for r in regions:
            try:
                es_client = target_account.get_client('opensearch', region=r)

                resource_item = {}
                resource_item['awsAccountId']                   = target_account.account_id
                resource_item['awsAccountName']                 = target_account.account_name
                resource_item['resourceType']                   = RESOURCE_TYPE
                resource_item['awsRegion']                      = r
                resource_item['source']                         = "Antiope"

                response = es_client.list_domain_names()  # This call doesn't support paganiation
                if 'DomainNames' not in response:
                    # No OS/ES domains in this region, move along
                    continue

                for d in response['DomainNames']:
                    domain_name = d['DomainName']
                    try:
                        response = es_client.describe_domains(DomainNames=[domain_name])
                    except ClientError as e:
                        if e.response['Error']['Code'] == "ThrottlingException":
                            # Wait a second and try again
                            sleep(1)
                            response = es_client.describe_domains(DomainNames=[domain_name])
                        else:
                            raise

                    domain = response['DomainStatusList'][0] # Boto3 returns an array, we ask for one domain, so we get one back

                    resource_item['configurationItemCaptureTime']   = str(datetime.datetime.now())
                    resource_item['configuration']                  = domain
                    resource_item['supplementaryConfiguration']     = {}
                    resource_item['resourceId']                     = domain['DomainId']
                    resource_item['resourceName']                   = domain['DomainName']
                    resource_item['ARN']                            = domain['ARN']
                    resource_item['errors']                         = {}
                    resource_item['supplementaryConfiguration']['EngineType'] = d['EngineType']

                    if domain['AccessPolicies']:
                        # The ES Domains' Access policy is returned as a string. Here we parse the json and reapply it to the dict
                        resource_item['supplementaryConfiguration']['AccessPolicies']  = json.loads(domain['AccessPolicies'])

                    try:
                        tags = es_client.list_tags(ARN=domain['ARN'])
                        if len(tags['TagList']) == 0:
                            resource_item['errors']['no_tags'] = True
                        else:
                            resource_item['tags'] = parse_tags(tags['TagList'])
                    except (ClientError, KeyError, IndexError) as e:
                        logger.error(f"Failed to get tags for {target_account.account_id}-{region}-{rds['DBInstanceIdentifier']}: {e}")
                        resource_item['errors']['no_tags'] = True

                    object_name = "{}-{}-{}".format(domain_name, r, target_account.account_id)
                    save_resource_to_s3(RESOURCE_PATH, object_name, resource_item)
                    sleep(1)

            except ClientError as e:
                # Move onto next region if we get access denied. This is probably SCPs
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    logger.error(f"AccessDeniedException for region {r} in function {context.function_name} for {target_account.account_name}({target_account.account_id})")
                    continue
                else:
                    raise  # pass on to the next handlier

    except AntiopeAssumeRoleError as e:
        logger.error("Unable to assume role into account {}({})".format(target_account.account_name, target_account.account_id))
        return()
    except ClientError as e:
        if e.response['Error']['Code'] == 'UnauthorizedOperation':
            logger.error("Antiope doesn't have proper permissions to this account")
            return(event)
        logger.critical("AWS Error getting info for {}: {}".format(message['account_id'], e))
        capture_error(message, context, e, "ClientError for {}: {}".format(message['account_id'], e))
        raise
    except Exception as e:
        logger.critical("{}\nMessage: {}\nContext: {}".format(e, message, vars(context)))
        capture_error(message, context, e, "General Exception for {}: {}".format(message['account_id'], e))
        raise
