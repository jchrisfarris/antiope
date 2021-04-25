from pprint import pprint
from google.cloud import resource_manager
from google.cloud import asset_v1

# To Do: Filter for desired resources via asset_type

def get_all_resources():
    """Prints out all resources within all projects based on access permissions"""
    # Get projects
    rmclient = resource_manager.Client()
    asclient = asset_v1.AssetServiceClient()
    for project in rmclient.list_projects():
        current_project = project.project_id
        # Get all resources in each project
        response = asclient.search_all_resources(
            request={
                "scope": f"projects/{current_project}",
            }
        )
        pprint(response)

    # Ex. output : 
        #    results {
        #      name: "//storage.googleapis.com/{bucket name}"
        #      asset_type: "storage.googleapis.com/Bucket"
        #      project: "projects/{project number}"
        #      display_name: "{bucket name}"
        #      location: "us-east1"
        #   }
    #

get_all_resources()
