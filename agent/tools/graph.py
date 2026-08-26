import ast
import os
import sys
from typing import Dict, List, Set, Any

from scan import parse_requirements

# Explicit mapping from import name to PyPI package name
IMPORT_TO_PKG = {
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
}

IGNORED_DIRS = {
    '.depgraph-venv',
    '.pytest_cache',
    '__pycache__',
    '.git',
    'venv',
    'env',
    '.env',
    'site-packages'
}

def normalize_pkg_name(name: str) -> str:
    return name.lower().replace('-', '_')

def is_standard_library(module_name: str) -> bool:
    if module_name in sys.builtin_module_names:
        return True
    if hasattr(sys, 'stdlib_module_names'):
        return module_name in sys.stdlib_module_names
    return False

def is_local_module(repo_path: str, module_name: str) -> bool:
    if os.path.isfile(os.path.join(repo_path, f"{module_name}.py")):
        return True
    if os.path.isdir(os.path.join(repo_path, module_name)):
        return True
    return False

def extract_imports_from_file(filepath: str) -> List[str]:
    try:
        # utf-8-sig strips the UTF-8 BOM (\xef\xbb\xbf / U+FEFF) that
        # Windows editors (VS Code, Notepad) prepend to .py files.  For
        # files without a BOM it behaves identically to plain utf-8.
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        print(
            f"[graph] WARNING: import extraction failed for {filepath}: {e}",
            file=sys.stderr,
        )
        return []

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split('.')[0]
                imports.add(top_level)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top_level = node.module.split('.')[0]
                if node.level == 0:
                    imports.add(top_level)
    return sorted(list(imports))

def build_dependency_graph(repo_path: str, requirements_path: str) -> Dict[str, Any]:
    reqs = []
    if os.path.exists(requirements_path):
        reqs = parse_requirements(requirements_path)
    
    declared_deps = {name: version for name, version in reqs}
    norm_to_orig = {normalize_pkg_name(name): name for name in declared_deps.keys()}
    
    files_data = []
    used_deps_set = set()
    unresolved_imports = 0
    third_party_imports = 0
    files_analyzed = 0
    
    for root, dirs, files in os.walk(repo_path):
        # Exclude ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.endswith('-env')]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, repo_path)
                rel_path = rel_path.replace('\\', '/')
                
                file_imports = extract_imports_from_file(filepath)
                files_analyzed += 1
                
                imports_data = []
                for imp in file_imports:
                    if is_standard_library(imp):
                        continue
                    if is_local_module(repo_path, imp):
                        continue
                    
                    third_party_imports += 1
                    
                    pkg_name = IMPORT_TO_PKG.get(imp, imp)
                    norm_pkg = normalize_pkg_name(pkg_name)
                    
                    matched_orig_req = norm_to_orig.get(norm_pkg)
                    if matched_orig_req:
                        used_deps_set.add(matched_orig_req)
                        imports_data.append({
                            "module": imp,
                            "dependency": matched_orig_req
                        })
                    else:
                        unresolved_imports += 1
                        imports_data.append({
                            "module": imp,
                            "dependency": None
                        })
                
                if imports_data:
                    files_data.append({
                        "path": rel_path,
                        "imports": imports_data
                    })
                    
    files_data.sort(key=lambda x: x["path"])
    for f in files_data:
        f["imports"].sort(key=lambda x: x["module"])
                    
    dependencies_data = []
    for name, version in declared_deps.items():
        dependencies_data.append({
            "name": name,
            "version": version,
            "used": name in used_deps_set
        })
    dependencies_data.sort(key=lambda x: x["name"])
    
    return {
        "repository": os.path.abspath(repo_path).replace('\\', '/'),
        "files": files_data,
        "dependencies": dependencies_data,
        "summary": {
            "files_analyzed": files_analyzed,
            "third_party_imports": third_party_imports,
            "declared_dependencies": len(declared_deps),
            "used_dependencies": len(used_deps_set),
            "unused_dependencies": len(declared_deps) - len(used_deps_set),
            "unresolved_imports": unresolved_imports
        }
    }
