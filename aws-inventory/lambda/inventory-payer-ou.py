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
from datetime import datetime, timezone, date
from dateutil import tz
from datetime import datetime as dt

from antiope.aws_account import *
from antiope.config import *
from antiope.aws_organization import *
from common import *

import logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, os.getenv('LOG_LEVEL', default='DEBUG')))
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


def lambda_handler(event, context):
    logger.debug("Received event: " + json.dumps(event, sort_keys=True))
    message = json.loads(event['Records'][0]['Sns']['Message'])
    logger.info("Received message: " + json.dumps(message, sort_keys=True))

    try:
        antiope_config = AntiopeConfig()
        payer_account = AWSAccount(message['payer_id'], config=antiope_config)
        org_client = payer_account.get_client('organizations')

        ou_map = {}

        # First lets get the root OU
        response = org_client.list_roots()
        root_ou = response['Roots'][0]['Id']

        account_list = []
        response = org_client.list_accounts(MaxResults=20)
        account_list = account_list + response['Accounts']
        while 'NextToken' in response:
            time.sleep(1) # Avoid Rate Limiting
            response = org_client.list_accounts(MaxResults=20, NextToken=response['NextToken'])
            account_list = account_list + response['Accounts']

        for a in account_list:
            # Build an array to reflect the parentage. We reverse this later.
            parentage = [a['Name']]

            parent_id = get_parent(org_client, a['Id'])
            while parent_id != root_ou:
                if parent_id not in ou_map:
                    ou_map[parent_id] = get_ou_name(org_client, parent_id)
                parentage.append(ou_map[parent_id])
                parent_id = get_parent(org_client, parent_id)

            # All Done. Append Root to the end and then generate a string
            parentage.append("Root")
            parentage.reverse()
            parentage_string = "/".join(parentage)

            # Add string as an attribute of the Account
            target_account = AWSAccount(a['Id'], config=antiope_config)
            target_account.update_attribute("OU_Path", parentage_string)
            target_account.update_attribute("Parent_OUs", parentage)


    except AntiopeAssumeRoleError as e:
        logger.error("Unable to assume role into account {}({})".format(payer_account.account_name, payer_account.account_id))
        return()
    except AntiopeAssumeRoleError as e:
        logger.error("Unable to assume role into account {}({})".format(payer_account.account_name, payer_account.account_id))
        return()
    except ClientError as e:
        if e.response['Error']['Code'] == 'AccessDeniedException':
            logger.error(f"AccessDeniedException for access-analyzer in {payer_account.account_name}({payer_account.account_id})")
            return()
        if e.response['Error']['Code'] == 'AWSOrganizationsNotInUseException':
            logger.warning(f"{message['payer_id']} is not an AWS organizations admin account")
            return()
        else:
            logger.critical("AWS Error getting info for {}: {}".format(message['payer_id'], e))
            capture_error(message, context, e, "ClientError for {}: {}".format(message['payer_id'], e))
            raise
    except Exception as e:
        # logger.critical("{}\nMessage: {}\nContext: {}".format(e, message, vars(context)))
        # capture_error(message, context, e, "General Exception for {}: {}".format(message['payer_id'], e))
        raise


def get_parent(org_client, id):
        response = org_client.list_parents(ChildId=id)
        if 'Parents' not in response or len(response['Parents']) == 0:
            # See note about NextToken in Boto3
            return(None)
        return(response['Parents'][0]['Id'])


def get_ou_name(org_client, id):
    response = org_client.describe_organizational_unit(OrganizationalUnitId=id)
    return(response['OrganizationalUnit']['Name'])


