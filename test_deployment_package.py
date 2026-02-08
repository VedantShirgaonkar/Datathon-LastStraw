#!/usr/bin/env python
"""
Test the Lambda deployment package before uploading to AWS.
Extracts the zip and verifies all imports work.
"""

import sys
import zipfile
import tempfile
import os
from pathlib import Path

def test_lambda_package():
    """Test the Lambda deployment package."""
    
    zip_path = Path("deployment/lambda_function.zip")
    
    if not zip_path.exists():
        print(f"❌ Zip file not found: {zip_path}")
        return False
    
    print(f"Testing deployment package: {zip_path}")
    print(f"File size: {zip_path.stat().st_size / (1024*1024):.2f} MB")
    print()
    
    # Extract to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Extracting to: {tmpdir}")
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(tmpdir)
        
        # List extracted contents
        print("\nExtracted structure:")
        for root, dirs, files in os.walk(tmpdir):
            level = root.replace(tmpdir, '').count(os.sep)
            indent = ' ' * 2 * level
            rel_path = os.path.relpath(root, tmpdir)
            if rel_path == '.':
                print(tmpdir)
            else:
                print(f'{indent}{rel_path}/')
            
            subindent = ' ' * 2 * (level + 1)
            for file in files[:5]:  # Show first 5 files
                print(f'{subindent}{file}')
            if len(files) > 5:
                print(f'{subindent}... and {len(files) - 5} more files')
        
        # Add to path and test imports
        print("\n" + "="*80)
        print("Testing imports...")
        print("="*80 + "\n")
        
        sys.path.insert(0, tmpdir)
        
        test_imports = [
            "agent.config",
            "agent.agent",
            "agent.kafka_consumer",
            "agent.schemas.tool_schemas",
            "agent.embedding_pipeline",
            "postgres",
            "clickhouse",
            "neo4j_db"
        ]
        
        failed = []
        
        for module in test_imports:
            try:
                __import__(module)
                print(f"✓ {module}")
            except ImportError as e:
                print(f"✗ {module}: {e}")
                failed.append((module, str(e)))
            except Exception as e:
                print(f"✗ {module}: {type(e).__name__}: {e}")
                failed.append((module, f"{type(e).__name__}: {e}"))
        
        print()
        
        # Test lambda handler specifically
        print("="*80)
        print("Testing Lambda handler...")
        print("="*80 + "\n")
        
        try:
            from agent.kafka_consumer import lambda_handler
            print("✓ Handler imported successfully")
            
            # Test with sample event
            test_event = {
                'eventSource': 'aws:kafka',
                'records': {
                    'events.github-0': [{
                        'topic': 'events.github',
                        'partition': 0,
                        'offset': 0,
                        'timestamp': 1707393600000,
                        'key': 'dGVzdA==',
                        'value': 'eyJldmVudF9pZCI6InRlc3QtMTIzIiwic291cmNlIjoiZ2l0aHViIiwiZXZlbnRfdHlwZSI6InB1c2giLCJ0aW1lc3RhbXAiOiIyMDI2LTAyLTA4VDEyOjAwOjAwWiIsInJhdyI6eyJjb21taXRzIjpbXX19',
                        'headers': []
                    }]
                }
            }
            
            result = lambda_handler(test_event, None)
            print(f"✓ Handler executed: {result}")
            
        except Exception as e:
            print(f"✗ Handler test failed: {e}")
            import traceback
            traceback.print_exc()
            failed.append(("lambda_handler", str(e)))
        
        print("\n" + "="*80)
        if failed:
            print(f"❌ FAILED: {len(failed)} import(s) failed")
            for module, error in failed:
                print(f"  - {module}: {error}")
            return False
        else:
            print("✅ SUCCESS: All imports and handler test passed!")
            return True

if __name__ == "__main__":
    success = test_lambda_package()
    sys.exit(0 if success else 1)
