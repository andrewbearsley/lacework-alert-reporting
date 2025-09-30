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
    
    def make_api_call_with_retry(self, api_call, max_retries=3, base_delay=1):
        """
        Make an API call with exponential backoff retry logic.
        
        Args:
            api_call: Function that makes the API call
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
            
        Returns:
            API response data
            
        Raises:
            Exception: If all retry attempts fail
        """
        for attempt in range(max_retries + 1):
            try:
                return api_call()
            except Exception as e:
                if attempt == max_retries:
                    raise e
                
                # Check if it's a rate limit error
                if hasattr(e, 'response') and e.response.status_code == 429:
                    delay = base_delay * (2 ** attempt)
                    print(f"Rate limit hit, waiting {delay}s before retry {attempt + 1}/{max_retries}")
                    time.sleep(delay)
                else:
                    # For other errors, wait a shorter time
                    delay = base_delay
                    print(f"API error, waiting {delay}s before retry {attempt + 1}/{max_retries}: {str(e)}")
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
