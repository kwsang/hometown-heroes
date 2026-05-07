from google.cloud import bigquery

class BigQueryService:
    def __init__(self, project_id: str):
        self.client = bigquery.Client(project=project_id)

    def get_all_hubs(self):
        """
        Fetches all unique regional hubs stored in BigQuery.
        """
        query = f"""
            SELECT 
                hometown_name as id,
                hometown_name as city, 
                lat, 
                lng,
                CONCAT('A collective hub for ', athlete_count, ' Team USA athletes.') as description
            FROM `{self.client.project}.team_usa_data.location_registry`
        """
        query_job = self.client.query(query)
        return [dict(row) for row in query_job.result()]

    def get_aggregate_hub_stats(self, region_id: str):
        """
        Fetches aggregate counts per sport for a region. 
        Strictly avoids individual identifiers.
        """
        query = f"""
            SELECT 
                sport_name, 
                athlete_count,
                athlete_ids,
                regional_elevation, # Assuming this is an average or representative elevation for the region
                lat, # Latitude of the region (e.g., city center)
                lng # Longitude of the region (e.g., city center)
            FROM `{self.client.project}.team_usa_data.hometown_hubs`
            WHERE region_id = @region_id
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("region_id", "STRING", region_id)
            ]
        )
        query_job = self.client.query(query, job_config=job_config)
        results = query_job.result()
        return [dict(row) for row in results]
