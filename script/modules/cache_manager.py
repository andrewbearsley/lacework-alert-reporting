"""
Cache management utilities for Lacework Alert Reporting.
"""
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional


class CacheManager:
    """Manages caching for various data types."""
    
    def __init__(self, cache_dir: Path):
        """Initialize cache manager with cache directory."""
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_cache_file_path(self, cache_type: str, identifier: str, suffix: str = "") -> Path:
        """Get cache file path for a specific type and identifier."""
        type_dir = self.cache_dir / cache_type
        type_dir.mkdir(exist_ok=True)
        
        if suffix:
            return type_dir / f"{identifier}_{suffix}.json"
        else:
            return type_dir / f"{identifier}.json"
    
    def get_resource_cache_file_path(self, cache_type: str, account_id: str, resource_type: str, start_date: str = None, end_date: str = None) -> Path:
        """Get cache file path for a specific resource type with account and date range."""
        type_dir = self.cache_dir / cache_type
        type_dir.mkdir(exist_ok=True)
        
        filename = generate_cache_filename(account_id, resource_type, start_date, end_date)
        return type_dir / filename
    
    def load_from_cache(self, cache_file: Path) -> Optional[Dict[str, Any]]:
        """Load data from cache file if it exists and is not expired."""
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            # Check if cache is expired (older than 24 hours)
            cached_at = datetime.fromisoformat(data.get('cached_at', ''))
            if datetime.now() - cached_at > timedelta(hours=24):
                return None
            
            return data
        except (json.JSONDecodeError, ValueError, KeyError):
            return None
    
    def save_to_cache(self, cache_file: Path, data: Dict[str, Any]) -> None:
        """Save data to cache file with timestamp."""
        data['cached_at'] = datetime.now().isoformat()
        
        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def clear_cache(self, cache_type: str = None) -> None:
        """Clear cache files. If cache_type is specified, only clear that type."""
        if cache_type:
            type_dir = self.cache_dir / cache_type
            if type_dir.exists():
                for file in type_dir.glob("*.json"):
                    file.unlink()
        else:
            # Clear all cache
            for file in self.cache_dir.rglob("*.json"):
                file.unlink()
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cache usage."""
        stats = {}
        for cache_type_dir in self.cache_dir.iterdir():
            if cache_type_dir.is_dir():
                count = len(list(cache_type_dir.glob("*.json")))
                stats[cache_type_dir.name] = count
        return stats


def generate_cache_filename(account_id: str, resource_type: str, start_date: str = None, end_date: str = None) -> str:
    """Generate cache filename with account, resource type, and date range."""
    # Clean resource type for filename (replace : with -)
    clean_resource_type = resource_type.replace(':', '-')
    
    # Build filename components
    filename_parts = [f"account_{account_id}", f"type_{clean_resource_type}"]
    
    # Add date range if provided
    if start_date and end_date:
        filename_parts.append(f"dates_{start_date}_to_{end_date}")
    
    return "_".join(filename_parts) + ".json"


def extract_account_id_from_arn(arn: str) -> Optional[str]:
    """Extract AWS account ID from ARN."""
    if not arn or not arn.startswith('arn:aws:'):
        return None
    
    parts = arn.split(':')
    if len(parts) >= 5:
        return parts[4]
    return None


def extract_resource_types_from_arns(arns: list) -> set:
    """Extract specific Lacework resource types from ARNs."""
    resource_types = set()
    for arn in arns:
        if arn and arn.startswith('arn:aws:'):
            parts = arn.split(':')
            if len(parts) >= 3:
                service = parts[2]
                
                # Special handling for S3 - bucket names are in parts[5] but we just want 's3:bucket'
                if service == 's3':
                    resource_types.add('s3:bucket')
                    continue
                
                # Special handling for ELB - use elbv2:loadbalancer instead of elasticloadbalancing:loadbalancer
                if service == 'elasticloadbalancing':
                    resource_types.add('elbv2:loadbalancer')
                    continue
                
                # Extract specific resource type from ARN
                if len(parts) >= 6:
                    resource_name = parts[5]  # e.g., "instance", "security-group", "vpc"
                    # Remove any resource ID after the resource type (e.g., "instance/i-123" -> "instance")
                    if '/' in resource_name:
                        resource_name = resource_name.split('/')[0]
                    lacework_type = f"{service}:{resource_name}"
                    resource_types.add(lacework_type)
                else:
                    # Fallback to service name if we can't determine specific type
                    resource_types.add(service)
    return resource_types


def map_aws_service_to_lacework_types(service: str) -> list:
    """Map AWS service name to Lacework resource types."""
    mapping = {
        'ec2': ['ec2:instance', 'ec2:security-group', 'ec2:vpc'],
        'iam': ['iam:role', 'iam:policy', 'iam:user'],
        'rds': ['rds:db', 'rds:db-cluster'],
        's3': ['s3:bucket'],
        'lambda': ['lambda:function'],
        'elasticloadbalancing': ['elbv2:loadbalancer'],
    }
    
    return mapping.get(service, [f"{service}:*"])

