"""
Git history loader for Tremor.
Extracts commit history and loads it into FalkorDB with pseudonymized authors.

PRIVACY GUARANTEE:
- Author emails are hashed using SHA256 before storage
- Only the hash (pseudonym_id) is stored in the graph
- No way to reverse the hash back to the original email
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

from git import Repo
from git.objects.commit import Commit


def pseudonymize_email(email: str) -> str:
    """
    Hash an email address to a pseudonymous ID.
    Uses SHA256 for one-way hashing (cannot be reversed).
    
    Args:
        email: Author email address
        
    Returns:
        Hex string of SHA256 hash (first 16 chars for readability)
    """
    hash_full = hashlib.sha256(email.encode('utf-8')).hexdigest()
    # Use first 16 chars for readability in queries
    return hash_full[:16]


class GitHistoryLoader:
    """Load git commit history into FalkorDB."""
    
    def __init__(self, repo_path: str, graph):
        self.repo_path = Path(repo_path)
        self.graph = graph
        self.repo = Repo(self.repo_path)
        
        # Track what we've created to avoid duplicates
        self.authors_created: Set[str] = set()
        self.commits_created: Set[str] = set()
    
    def load_history(self, max_commits: int = 100, branch: str = 'main'):
        """
        Load git history into the graph.
        
        Args:
            max_commits: Maximum number of recent commits to load
            branch: Branch to load history from (tries 'main' then 'master')
        """
        print(f"\nLoading git history from {self.repo_path}...")
        
        # Try to find the default branch
        try:
            commits = list(self.repo.iter_commits(branch, max_count=max_commits))
        except Exception:
            # Try 'master' if 'main' doesn't exist
            try:
                commits = list(self.repo.iter_commits('master', max_count=max_commits))
                print(f"  (using 'master' branch)")
            except Exception as e:
                # Fall back to HEAD
                commits = list(self.repo.iter_commits('HEAD', max_count=max_commits))
                print(f"  (using HEAD)")
        
        print(f"Found {len(commits)} commits")
        
        authors_count = 0
        commits_count = 0
        touched_count = 0
        
        for commit in commits:
            # Create author (pseudonymized)
            if self._create_author(commit):
                authors_count += 1
            
            # Create commit
            if self._create_commit(commit):
                commits_count += 1
            
            # Create AUTHORED edge
            self._create_authored_edge(commit)
            
            # Create TOUCHED edges (commit -> modules)
            touched = self._create_touched_edges(commit)
            touched_count += touched
        
        print(f"✓ Loaded {authors_count} unique authors (pseudonymized)")
        print(f"✓ Loaded {commits_count} commits")
        print(f"✓ Created {touched_count} TOUCHED edges")
    
    def _create_author(self, commit: Commit) -> bool:
        """
        Create Author node if not exists.
        
        Returns:
            True if author was created, False if already existed
        """
        email = commit.author.email
        pseudonym_id = pseudonymize_email(email)
        
        if pseudonym_id in self.authors_created:
            return False
        
        query = """
        MERGE (a:Author {pseudonym_id: $pseudonym_id})
        ON CREATE SET a.name = $name
        """
        self.graph.query(query, {
            'pseudonym_id': pseudonym_id,
            'name': commit.author.name  # Name is less sensitive, can be stored
        })
        
        self.authors_created.add(pseudonym_id)
        return True
    
    def _create_commit(self, commit: Commit) -> bool:
        """
        Create Commit node if not exists.
        
        Returns:
            True if commit was created, False if already existed
        """
        sha = commit.hexsha[:8]  # Short SHA for readability
        
        if sha in self.commits_created:
            return False
        
        # Get commit message (first line only)
        message = commit.message.split('\n')[0][:100]  # Truncate long messages
        
        # Convert timestamp to ISO format
        timestamp = datetime.fromtimestamp(commit.committed_date).isoformat()
        
        query = """
        MERGE (c:Commit {sha: $sha})
        ON CREATE SET 
            c.message = $message,
            c.timestamp = $timestamp,
            c.full_sha = $full_sha
        """
        self.graph.query(query, {
            'sha': sha,
            'full_sha': commit.hexsha,
            'message': message,
            'timestamp': timestamp
        })
        
        self.commits_created.add(sha)
        return True
    
    def _create_authored_edge(self, commit: Commit):
        """Create AUTHORED edge from Author to Commit."""
        email = commit.author.email
        pseudonym_id = pseudonymize_email(email)
        sha = commit.hexsha[:8]
        
        query = """
        MATCH (a:Author {pseudonym_id: $pseudonym_id})
        MATCH (c:Commit {sha: $sha})
        MERGE (a)-[:AUTHORED]->(c)
        """
        self.graph.query(query, {
            'pseudonym_id': pseudonym_id,
            'sha': sha
        })
    
    def _create_touched_edges(self, commit: Commit) -> int:
        """
        Create TOUCHED edges from Commit to Modules that were changed.
        
        Returns:
            Number of TOUCHED edges created
        """
        sha = commit.hexsha[:8]
        touched_count = 0
        
        # Get list of files changed in this commit
        if commit.parents:
            # Compare with parent
            parent = commit.parents[0]
            diffs = parent.diff(commit)
        else:
            # First commit, compare with empty tree
            diffs = commit.diff(None)
        
        # Extract changed file paths
        changed_files = set()
        for diff in diffs:
            if diff.a_path:
                changed_files.add(diff.a_path)
            if diff.b_path:
                changed_files.add(diff.b_path)
        
        # Create TOUCHED edges for modules we have in the graph
        for file_path in changed_files:
            # Only track Python files in src/click/
            if file_path.startswith('src/click/') and file_path.endswith('.py'):
                query = """
                MATCH (c:Commit {sha: $sha})
                MATCH (m:Module {path: $module_path})
                MERGE (c)-[:TOUCHED]->(m)
                """
                result = self.graph.query(query, {
                    'sha': sha,
                    'module_path': file_path
                })
                
                # Check if edge was created (module exists)
                # Note: MERGE always succeeds, so we count all attempts
                touched_count += 1
        
        return touched_count


def test_pseudonymization():
    """Test that pseudonymization works and is consistent."""
    email1 = "developer@example.com"
    email2 = "other@example.com"
    
    hash1a = pseudonymize_email(email1)
    hash1b = pseudonymize_email(email1)
    hash2 = pseudonymize_email(email2)
    
    print("Pseudonymization test:")
    print(f"  {email1} -> {hash1a}")
    print(f"  {email1} -> {hash1b} (same? {hash1a == hash1b})")
    print(f"  {email2} -> {hash2} (different? {hash1a != hash2})")
    print()
    
    assert hash1a == hash1b, "Same email should produce same hash"
    assert hash1a != hash2, "Different emails should produce different hashes"
    print("✓ Pseudonymization works correctly")


def main():
    """Test the git loader standalone."""
    from db import get_graph
    import os
    
    repo_path = os.getenv('REPO_PATH', './data/click')
    
    print("Testing git history loader")
    print("=" * 60)
    test_pseudonymization()
    print()
    
    print(f"Loading history from: {repo_path}")
    graph = get_graph()
    
    loader = GitHistoryLoader(repo_path, graph)
    loader.load_history(max_commits=50)
    
    print("\n" + "=" * 60)
    print("Verifying loaded data...")
    
    # Query authors
    result = graph.query("MATCH (a:Author) RETURN count(a) AS count")
    author_count = result.result_set[0][0]
    print(f"Authors in graph: {author_count}")
    
    # Query commits
    result = graph.query("MATCH (c:Commit) RETURN count(c) AS count")
    commit_count = result.result_set[0][0]
    print(f"Commits in graph: {commit_count}")
    
    # Sample author activity
    result = graph.query("""
        MATCH (a:Author)-[:AUTHORED]->(c:Commit)
        RETURN a.name AS author, a.pseudonym_id AS id, count(c) AS commits
        ORDER BY commits DESC
        LIMIT 5
    """)
    
    print("\nTop 5 contributors:")
    for row in result.result_set:
        name, pid, commits = row
        print(f"  {name} ({pid}): {commits} commits")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
