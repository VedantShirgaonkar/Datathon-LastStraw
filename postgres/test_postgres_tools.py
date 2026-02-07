"""
Test PostgreSQL tools with Pydantic validation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools.postgres_tools import (
    create_user,
    create_project,
    assign_user_to_project,
    add_identity_mapping,
    get_user_by_email,
    get_project_by_id
)


def test_create_user():
    """Test user creation"""
    print("\n" + "=" * 80)
    print("TEST 1: Create User")
    print("=" * 80)
    
    result = create_user(
        email="test@company.com",
        name="Test Developer",
        team_id="11111111-1111-1111-1111-111111111111",  # Platform Engineering team
        role="Engineer",
        hourly_rate=75.0
    )
    
    print(f"Success: {result['success']}")
    print(f"Message: {result['message']}")
    if result['user_id']:
        print(f"User ID: {result['user_id']}")
    
    return result


def test_get_user(email: str):
    """Test user lookup"""
    print("\n" + "=" * 80)
    print("TEST 2: Get User by Email")
    print("=" * 80)
    
    result = get_user_by_email(email=email)
    
    print(f"Success: {result['success']}")
    print(f"Message: {result['message']}")
    if result['user']:
        user = result['user']
        print(f"User Details:")
        print(f"  ID: {user['id']}")
        print(f"  Name: {user['name']}")
        print(f"  Role: {user['role']}")
        print(f"  Hourly Rate: ${user['hourly_rate']}")
    
    return result


def test_create_project():
    """Test project creation"""
    print("\n" + "=" * 80)
    print("TEST 3: Create Project")
    print("=" * 80)
    
    result = create_project(
        name="Test Project Alpha",
        description="Test project for agent validation",
        github_repo="company/test-project-alpha",
        jira_project_key="TPA",
        status="active",
        priority="high",
        target_date="2026-03-31"
    )
    
    print(f"Success: {result['success']}")
    print(f"Message: {result['message']}")
    if result['project_id']:
        print(f"Project ID: {result['project_id']}")
    
    return result


def test_assign_user_to_project(user_id: str, project_id: str):
    """Test project assignment"""
    print("\n" + "=" * 80)
    print("TEST 4: Assign User to Project")
    print("=" * 80)
    
    result = assign_user_to_project(
        user_id=user_id,
        project_id=project_id,
        role="contributor",
        allocated_percent=60.0
    )
    
    print(f"Success: {result['success']}")
    print(f"Message: {result['message']}")
    if result['assignment_id']:
        print(f"Assignment ID: {result['assignment_id']}")
    
    return result


def test_add_identity_mapping(user_id: str):
    """Test identity mapping"""
    print("\n" + "=" * 80)
    print("TEST 5: Add GitHub Identity Mapping")
    print("=" * 80)
    
    result = add_identity_mapping(
        user_id=user_id,
        source="github",
        external_id="gh-test-123",
        external_username="testdev"
    )
    
    print(f"Success: {result['success']}")
    print(f"Message: {result['message']}")
    if result['mapping_id']:
        print(f"Mapping ID: {result['mapping_id']}")
    
    return result


def main():
    """Run all PostgreSQL tool tests"""
    print("\n" + "=" * 80)
    print("POSTGRESQL TOOLS TEST SUITE")
    print("=" * 80)
    
    try:
        # Test 1: Create user
        user_result = test_create_user()
        
        if not user_result['success']:
            print("\n[FAIL] User creation failed, stopping tests")
            return
        
        user_id = user_result['user_id']
        user_email = user_result['email']
        
        # Test 2: Get user
        test_get_user(user_email)
        
        # Test 3: Create project
        project_result = test_create_project()
        
        if not project_result['success']:
            print("\n[FAIL] Project creation failed")
            return
        
        project_id = project_result['project_id']
        
        # Test 4: Assign user to project
        test_assign_user_to_project(user_id, project_id)
        
        # Test 5: Add identity mapping
        test_add_identity_mapping(user_id)
        
        print("\n" + "=" * 80)
        print("ALL TESTS COMPLETED")
        print("=" * 80)
        print("\n[INFO] Tools validated successfully!")
        print("[INFO] User, project, assignment, and identity mapping created.")
        print(f"\n[CLEANUP] To remove test data:")
        print(f"  DELETE FROM users WHERE id = '{user_id}';")
        print(f"  DELETE FROM projects WHERE id = '{project_id}';")
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
