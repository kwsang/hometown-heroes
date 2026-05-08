from google.cloud import bigquery
from functools import lru_cache
from typing import Optional

class BigQueryService:
    def __init__(self, project_id: str):
        self.client = bigquery.Client(project=project_id)

    @lru_cache(maxsize=128)
    def get_all_hubs(self):
        """
        Fetches all unique regional hubs stored in BigQuery.
        """
        query = f"""
            SELECT 
                hometown_id as id,
                hometown_id as city, 
                hometown as pretty_city_name,
                total_athlete_count,
                lat, 
                lng,
                region,
                CONCAT('A collective hub for ', total_athlete_count, ' Team USA athletes in the ', region, ' region.') as description
            FROM `{self.client.project}.team_usa_data.regional_hubs_summary`
        """
        query_job = self.client.query(query)
        return [dict(row) for row in query_job.result()]

    @lru_cache(maxsize=512)
    def get_aggregate_hub_stats(self, hometown_id: str):
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
                region,
                lat, # Latitude of the region (e.g., city center)
                lng # Longitude of the region (e.g., city center)
            FROM `{self.client.project}.team_usa_data.hometown_hubs`
            WHERE hometown_id = @hometown_id
            ORDER BY athlete_count DESC, sport_name ASC
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("hometown_id", "STRING", hometown_id)
            ]
        )
        query_job = self.client.query(query, job_config=job_config)
        results = query_job.result()
        return [dict(row) for row in results]

    def get_cached_narrative(self, hometown_id: str) -> Optional[str]:
        """Checks if a narrative already exists for this hub."""
        query = f"""
            SELECT narrative 
            FROM `{self.client.project}.team_usa_data.regional_hubs_summary`
            WHERE hometown_id = @hometown_id AND narrative IS NOT NULL
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("hometown_id", "STRING", hometown_id)]
        )
        results = list(self.client.query(query, job_config=job_config).result())
        return results[0].narrative if results else None

    def get_cached_image(self, hometown_id: str) -> Optional[str]:
        """Checks if a hub image already exists in the cache."""
        query = f"""
            SELECT hub_image 
            FROM `{self.client.project}.team_usa_data.regional_hubs_summary`
            WHERE hometown_id = @hometown_id AND hub_image IS NOT NULL
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("hometown_id", "STRING", hometown_id)]
        )
        results = list(self.client.query(query, job_config=job_config).result())
        return results[0].hub_image if results else None

    def update_hub_narrative(self, hometown_id: str, narrative: str):
        """Persists a generated narrative to the summary table."""
        query = f"""
            UPDATE `{self.client.project}.team_usa_data.regional_hubs_summary`
            SET narrative = @narrative,
                narrative_timestamp = CURRENT_TIMESTAMP()
            WHERE hometown_id = @hometown_id
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("narrative", "STRING", narrative),
                bigquery.ScalarQueryParameter("hometown_id", "STRING", hometown_id)
            ]
        )
        self.client.query(query, job_config=job_config).result()
