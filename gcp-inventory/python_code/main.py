from google.cloud import asset_v1
import logging
import os

def main(event, data):
    """Prints out all resources within all projects based on access permissions"""
    # Get All Resources Insied Passed Organization
    asclient = asset_v1.AssetServiceClient()
    organization_to_query = os.environ.get('ORGANIZATION', 'Specified environment variable is not set.')
    response = asclient.search_all_resources(
        request={
            "scope": f"organizations/{organization_to_query}",
        }
    )
    logging.info(f"Response for query against {response}")

    # Ex. output : 
        #    results {
        #      name: "//storage.googleapis.com/{bucket name}"
        #      asset_type: "storage.googleapis.com/Bucket"
        #      project: "projects/{project number}"
        #      display_name: "{bucket name}"
        #      location: "us-east1"
        #   }
    #

def parse_all_resources(data):
    # To Do: Parse of data
    pass
