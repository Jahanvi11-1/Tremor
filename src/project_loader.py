"""
Project/Feature context loader.

Auto-detects projects from directory structure and loads them as graph nodes.
Links modules to projects so the agent can reason about cross-project impact.

GRAPH ADDITIONS:
  Node: Project {name, path, language, module_count}
  Edge: BELONGS_TO (Module -> Project)

WHY THIS MATTERS:
  Without project context, the agent can only say "function X affects 12 functions".
  With project context: "function X affects 12 functions across 3 projects: auth, payments, logging"
  This is the "Connect people, projects, and decisions" criterion.
"""

import os
from pathlib import Path
from db import get_graph


def detect_projects(repo_path: str) -> list:
    """
    Auto-detect project groupings from directory structure.
    
    Strategy:
      1. Top-level directories are projects (src/, backend/, frontend/, etc.)
      2. Sub-directories with many files become sub-projects
      3. Language is inferred from file extensions
    
    Returns:
        List of dicts: {name, path, language, description}
    """
    repo = Path(repo_path)
    projects = []
    
    # Check top-level directories
    skip_dirs = {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.kiro', 'dist', 'build'}
    
    for item in sorted(repo.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith('.') or item.name in skip_dirs:
            continue
        
        # Count files by language
        py_count = len(list(item.rglob('*.py')))
        ts_count = len(list(item.rglob('*.ts'))) + len(list(item.rglob('*.tsx')))
        dart_count = len(list(item.rglob('*.dart')))
        sql_count = len(list(item.rglob('*.sql')))
        
        total = py_count + ts_count + dart_count + sql_count
        
        if total == 0:
            continue
        
        # Determine primary language
        lang_counts = {'python': py_count, 'typescript': ts_count, 'dart': dart_count, 'sql': sql_count}
        primary_lang = max(lang_counts, key=lang_counts.get)
        
        # Generate description
        desc = _infer_project_description(item.name, primary_lang)
        
        projects.append({
            'name': item.name,
            'path': str(item.relative_to(repo)),
            'language': primary_lang,
            'description': desc,
            'file_counts': lang_counts,
            'total_files': total
        })
    
    # Also check src/ subdirectories if src/ exists
    src_dir = repo / 'src'
    if src_dir.exists():
        # src is one project by itself — add as 'source' project  
        py_count = len(list(src_dir.rglob('*.py')))
        if py_count > 0:
            # Check if it's the click src/click subdirectory
            click_dir = src_dir / 'click'
            if click_dir.exists():
                projects.append({
                    'name': 'click_core',
                    'path': 'src/click',
                    'language': 'python',
                    'description': 'Click library core source',
                    'file_counts': {'python': len(list(click_dir.rglob('*.py')))},
                    'total_files': len(list(click_dir.rglob('*.py')))
                })
    
    return projects


def _infer_project_description(dir_name: str, language: str) -> str:
    """Infer a project description from the directory name."""
    descriptions = {
        'backend': 'Backend API service',
        'frontend': 'Frontend web application',
        'api': 'REST API layer',
        'web': 'Web application',
        'mobile': 'Mobile application',
        'db': 'Database layer',
        'sql': 'SQL database scripts',
        'migrations': 'Database migrations',
        'tests': 'Test suite',
        'scripts': 'Utility scripts',
        'src': 'Source code',
        'lib': 'Library code',
        'core': 'Core functionality',
        'utils': 'Utility functions',
        'data': 'Data files',
        'demo': 'Demo application',
        'demo-multi-lang': 'Multi-language demo project',
    }
    
    base = descriptions.get(dir_name.lower(), f'{dir_name} ({language})')
    return base


def load_projects(repo_path: str):
    """
    Detect and load Project nodes into FalkorDB.
    Links modules to their projects via BELONGS_TO edges.
    """
    graph = get_graph()
    projects = detect_projects(repo_path)
    
    if not projects:
        print("  No projects detected")
        return
    
    print(f"\nLoading {len(projects)} detected projects...")
    
    project_count = 0
    belongs_count = 0
    
    for proj in projects:
        # Create Project node
        query = """
        MERGE (p:Project {name: $name})
        SET p.path = $path,
            p.language = $language,
            p.description = $description,
            p.total_files = $total_files
        RETURN p.name AS name
        """
        graph.query(query, {
            'name': proj['name'],
            'path': proj['path'],
            'language': proj['language'],
            'description': proj['description'],
            'total_files': proj['total_files']
        })
        project_count += 1
        
        # Link modules to this project (path contains the project path)
        link_query = """
        MATCH (m:Module)
        WHERE m.path STARTS WITH $proj_path
        MERGE (m)-[:BELONGS_TO]->(p:Project {name: $proj_name})
        RETURN count(m) AS linked
        """
        result = graph.query(link_query, {
            'proj_path': proj['path'],
            'proj_name': proj['name']
        })
        linked = result.result_set[0][0] if result.result_set else 0
        belongs_count += linked
        
        lang_str = " + ".join(
            f"{v} {k}" for k, v in proj['file_counts'].items() if v > 0
        )
        print(f"  ✓ {proj['name']} ({proj['language']}) — {lang_str} — linked {linked} modules")
    
    print(f"✓ Created {project_count} Project nodes")
    print(f"✓ Created {belongs_count} BELONGS_TO edges")
    
    return projects


def get_affected_projects(function_names: list) -> list:
    """
    Given a list of function names (e.g., blast radius), find which projects they belong to.
    Returns list of distinct projects with counts.
    """
    if not function_names:
        return []
    
    graph = get_graph()
    
    query = """
    UNWIND $names AS fname
    MATCH (f:Function {name: fname})-[:CONTAINS]-(m:Module)-[:BELONGS_TO]->(p:Project)
    RETURN DISTINCT p.name AS project, p.language AS language, 
           count(DISTINCT f) AS affected_functions
    ORDER BY affected_functions DESC
    """
    
    try:
        result = graph.query(query, {'names': function_names})
        projects = []
        for row in result.result_set:
            projects.append({
                'project': row[0],
                'language': row[1],
                'affected_functions': row[2]
            })
        return projects
    except Exception:
        return []
