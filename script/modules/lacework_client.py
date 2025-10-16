"""
Lacework API client wrapper and authentication management.
"""
import time
from laceworksdk import LaceworkClient


class LaceworkClientWrapper:
    """Wrapper for Lacework API client with error handling and retry logic."""
    
    def __init__(self, credentials):
        """Initialize the Lacework client with credentials."""
        self.credentials = credentials
        self.client = LaceworkClient(
            account=credentials['account'],
            api_key=credentials['keyId'],
            api_secret=credentials['secret']
        )
    
    def get_client(self):
        """Get the underlying Lacework client."""
        return self.client
    
    def make_api_call_with_retry(self, api_call, max_retries=5, backoff_intervals=None):
        """
        Make an API call with progressive backoff retry logic.
        
        Args:
            api_call: Function that makes the API call
            max_retries: Maximum number of retry attempts
            backoff_intervals: List of delays in seconds for each retry [10, 20, 30, 60, 120]
            
        Returns:
            API response data
            
        Raises:
            Exception: If all retry attempts fail
        """
        if backoff_intervals is None:
            backoff_intervals = [60, 60, 60, 60, 60]  # Lacework requires 60s between rate-limited requests
        
        for attempt in range(max_retries):
            try:
                return api_call()
            except Exception as e:
                error_str = str(e)
                is_rate_limit = '429' in error_str or 'Rate Limit' in error_str or (hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429)
                
                if attempt == max_retries - 1:
                    raise e
                
                if is_rate_limit:
                    delay = backoff_intervals[attempt] if attempt < len(backoff_intervals) else backoff_intervals[-1]
                    print(f"      ⏳ Rate limit hit (SDK), waiting {delay}s (retry {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    # For other errors, still retry with backoff
                    delay = backoff_intervals[attempt] if attempt < len(backoff_intervals) else backoff_intervals[-1]
                    print(f"      ⚠️ API error, waiting {delay}s (retry {attempt + 1}/{max_retries}): {str(e)[:100]}")
                    time.sleep(delay)
        
        raise Exception("Max retries exceeded")
    
    def search_resources(self, search_request):
        """
        Search for resources using the Lacework API with retry logic.
        
        Args:
            search_request: Search request parameters
            
        Returns:
            Search results
        """
        def api_call():
            return self.client.inventory.search(search_request)
        
        return self.make_api_call_with_retry(api_call)
    
    def get_aws_accounts(self):
        """
        Get configured AWS accounts with retry logic.
        
        Returns:
            List of AWS accounts
        """
        def api_call():
            return self.client.cloud_accounts.get_by_type("AwsCfg")
        
        return self.make_api_call_with_retry(api_call)
