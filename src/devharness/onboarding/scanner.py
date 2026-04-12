"""Codebase scanner -- analyzes a workspace directory to produce a CodebaseProfile.

Walks the file tree (respecting common ignore patterns), counts files by extension,
reads config files to detect frameworks/tooling, and classifies the project type.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# Directories to skip when scanning
_IGNORE_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".tox", ".nox", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".venv", "venv", "env", ".env",
    "dist", "build", "_build", "target", "out", ".next", ".nuxt",
    ".devharness", ".idea", ".vscode",
    "vendor", "third_party", "3rdparty",
    "coverage", "htmlcov", ".coverage",
})

# Extension -> language mapping
_EXT_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".php": "php",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".scala": "scala",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
}


@dataclass
class CodebaseProfile:
    """Everything the harness learned about the codebase."""

    languages: dict[str, int] = field(default_factory=dict)
    primary_language: str = "unknown"
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    test_frameworks: list[str] = field(default_factory=list)
    test_command: str = ""
    lint_command: str = ""
    format_command: str = ""
    build_command: str = ""
    type_check_command: str = ""
    dev_server_command: str | None = None
    entry_points: list[str] = field(default_factory=list)
    has_ci: bool = False
    ci_system: str | None = None
    has_docker: bool = False
    has_makefile: bool = False
    readme_path: str | None = None
    config_files: list[str] = field(default_factory=list)
    directory_structure: dict[str, list[str]] = field(default_factory=dict)
    estimated_size: str = "small"
    web_app: bool = False
    api_app: bool = False
    cli_app: bool = False
    library: bool = False


class CodebaseScanner:
    """Scans a workspace directory and produces a CodebaseProfile."""

    def __init__(self, workspace: Path | None = None, *, workspace_root: str | Path = ".") -> None:
        if workspace is not None:
            self.workspace = Path(workspace).resolve()
        else:
            self.workspace = Path(workspace_root).resolve()

    def scan(self) -> CodebaseProfile:
        """Run all detection passes and return a complete profile."""
        profile = CodebaseProfile()

        self._count_files(profile)
        self._detect_primary_language(profile)
        self._detect_config_files(profile)
        self._detect_package_managers(profile)
        self._detect_ci(profile)
        self._detect_docker(profile)
        self._detect_makefile(profile)
        self._detect_readme(profile)
        self._detect_directory_structure(profile)
        self._detect_entry_points(profile)

        # These depend on config files being detected first
        self._detect_frameworks(profile)
        self._detect_test_frameworks(profile)
        self._detect_commands(profile)
        self._classify_project_type(profile)

        return profile

    # ------------------------------------------------------------------
    # File counting
    # ------------------------------------------------------------------

    def _count_files(self, profile: CodebaseProfile) -> None:
        total = 0
        for path in self._walk_files():
            ext = path.suffix.lower()
            lang = _EXT_LANGUAGE.get(ext)
            if lang:
                profile.languages[lang] = profile.languages.get(lang, 0) + 1
            total += 1

        if total < 1000:
            profile.estimated_size = "small"
        elif total < 10_000:
            profile.estimated_size = "medium"
        else:
            profile.estimated_size = "large"

    def _detect_primary_language(self, profile: CodebaseProfile) -> None:
        if profile.languages:
            profile.primary_language = max(profile.languages, key=profile.languages.get)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Config files
    # ------------------------------------------------------------------

    def _detect_config_files(self, profile: CodebaseProfile) -> None:
        candidates = [
            "pyproject.toml", "setup.py", "setup.cfg",
            "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            "Cargo.toml", "go.mod", "go.sum",
            "Gemfile", "composer.json", "pom.xml", "build.gradle", "build.gradle.kts",
            "tsconfig.json", "jsconfig.json",
            "tox.ini", "Makefile", "CMakeLists.txt",
            ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml",
            "eslint.config.js", "eslint.config.mjs",
            ".prettierrc", ".prettierrc.json", ".prettierrc.js",
            "prettier.config.js", "prettier.config.mjs",
            "ruff.toml", ".flake8",
            "mypy.ini", ".mypy.ini",
            "vite.config.ts", "vite.config.js",
            "next.config.js", "next.config.mjs", "next.config.ts",
            "webpack.config.js", "webpack.config.ts",
            "tailwind.config.js", "tailwind.config.ts",
            "jest.config.js", "jest.config.ts", "jest.config.mjs",
            "vitest.config.ts", "vitest.config.js",
            "pytest.ini", "conftest.py",
            ".babelrc", "babel.config.js",
        ]
        for name in candidates:
            if (self.workspace / name).exists():
                profile.config_files.append(name)

    # ------------------------------------------------------------------
    # Package managers
    # ------------------------------------------------------------------

    def _detect_package_managers(self, profile: CodebaseProfile) -> None:
        checks = [
            (["pyproject.toml", "setup.py", "setup.cfg"], "pip"),
            (["Pipfile"], "pipenv"),
            (["poetry.lock"], "poetry"),
            (["package.json"], "npm"),
            (["yarn.lock"], "yarn"),
            (["pnpm-lock.yaml"], "pnpm"),
            (["Cargo.toml"], "cargo"),
            (["go.mod"], "go mod"),
            (["Gemfile"], "bundler"),
            (["composer.json"], "composer"),
            (["pom.xml"], "maven"),
            (["build.gradle", "build.gradle.kts"], "gradle"),
        ]
        for files, manager in checks:
            if any((self.workspace / f).exists() for f in files):
                profile.package_managers.append(manager)

        # Refine pip vs poetry
        if "pip" in profile.package_managers and "poetry" in profile.package_managers:
            profile.package_managers.remove("pip")

    # ------------------------------------------------------------------
    # CI
    # ------------------------------------------------------------------

    def _detect_ci(self, profile: CodebaseProfile) -> None:
        ci_checks = [
            (self.workspace / ".github" / "workflows", "github actions"),
            (self.workspace / ".gitlab-ci.yml", "gitlab ci"),
            (self.workspace / "Jenkinsfile", "jenkins"),
            (self.workspace / ".circleci", "circleci"),
            (self.workspace / ".travis.yml", "travis ci"),
            (self.workspace / "azure-pipelines.yml", "azure pipelines"),
            (self.workspace / "bitbucket-pipelines.yml", "bitbucket pipelines"),
        ]
        for path, system in ci_checks:
            if path.exists():
                profile.has_ci = True
                profile.ci_system = system
                break

    # ------------------------------------------------------------------
    # Docker / Makefile / README
    # ------------------------------------------------------------------

    def _detect_docker(self, profile: CodebaseProfile) -> None:
        profile.has_docker = (
            (self.workspace / "Dockerfile").exists()
            or (self.workspace / "docker-compose.yml").exists()
            or (self.workspace / "docker-compose.yaml").exists()
            or (self.workspace / "compose.yml").exists()
            or (self.workspace / "compose.yaml").exists()
        )

    def _detect_makefile(self, profile: CodebaseProfile) -> None:
        profile.has_makefile = (self.workspace / "Makefile").exists()

    def _detect_readme(self, profile: CodebaseProfile) -> None:
        for name in ("README.md", "README.rst", "README.txt", "README", "readme.md"):
            if (self.workspace / name).exists():
                profile.readme_path = name
                break

    # ------------------------------------------------------------------
    # Directory structure
    # ------------------------------------------------------------------

    def _detect_directory_structure(self, profile: CodebaseProfile) -> None:
        for child in sorted(self.workspace.iterdir()):
            if child.name.startswith(".") or child.name in _IGNORE_DIRS:
                continue
            if child.is_dir():
                notable: list[str] = []
                try:
                    for item in sorted(child.iterdir()):
                        if item.is_file() and not item.name.startswith("."):
                            notable.append(item.name)
                        if len(notable) >= 10:
                            break
                except PermissionError:
                    pass
                profile.directory_structure[child.name] = notable

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def _detect_entry_points(self, profile: CodebaseProfile) -> None:
        candidates = [
            "main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py",
            "cli.py", "__main__.py",
            "index.ts", "index.js", "main.ts", "main.js",
            "app.ts", "app.js", "server.ts", "server.js",
            "main.go", "main.rs",
            "src/main.py", "src/app.py", "src/index.ts", "src/index.js",
            "src/main.ts", "src/main.js", "src/main.go", "src/main.rs",
            "src/lib.rs",
        ]
        for candidate in candidates:
            if (self.workspace / candidate).exists():
                profile.entry_points.append(candidate)

    # ------------------------------------------------------------------
    # Framework detection
    # ------------------------------------------------------------------

    def _detect_frameworks(self, profile: CodebaseProfile) -> None:
        # Python frameworks -- check pyproject.toml and setup.py
        pyproject = self.workspace / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text(errors="replace")
                self._detect_python_frameworks(content, profile)
            except OSError:
                pass

        setup_py = self.workspace / "setup.py"
        if setup_py.exists():
            try:
                content = setup_py.read_text(errors="replace")
                self._detect_python_frameworks(content, profile)
            except OSError:
                pass

        # JS/TS frameworks -- check package.json
        pkg_json = self.workspace / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(errors="replace"))
                deps = {}
                deps.update(pkg.get("dependencies", {}))
                deps.update(pkg.get("devDependencies", {}))
                self._detect_js_frameworks(deps, profile)
            except (OSError, json.JSONDecodeError):
                pass

        # Rust frameworks -- check Cargo.toml
        cargo = self.workspace / "Cargo.toml"
        if cargo.exists():
            try:
                content = cargo.read_text(errors="replace")
                if "actix-web" in content:
                    profile.frameworks.append("actix-web")
                if "axum" in content:
                    profile.frameworks.append("axum")
                if "rocket" in content:
                    profile.frameworks.append("rocket")
                if "clap" in content:
                    profile.frameworks.append("clap")
            except OSError:
                pass

        # Go frameworks -- check go.mod
        gomod = self.workspace / "go.mod"
        if gomod.exists():
            try:
                content = gomod.read_text(errors="replace")
                if "gin-gonic/gin" in content:
                    profile.frameworks.append("gin")
                if "labstack/echo" in content:
                    profile.frameworks.append("echo")
                if "gorilla/mux" in content:
                    profile.frameworks.append("gorilla")
                if "go-chi/chi" in content:
                    profile.frameworks.append("chi")
                if "spf13/cobra" in content:
                    profile.frameworks.append("cobra")
            except OSError:
                pass

        # Deduplicate
        profile.frameworks = list(dict.fromkeys(profile.frameworks))

    def _detect_python_frameworks(self, content: str, profile: CodebaseProfile) -> None:
        framework_markers = {
            "flask": "flask",
            "django": "django",
            "fastapi": "fastapi",
            "starlette": "starlette",
            "tornado": "tornado",
            "aiohttp": "aiohttp",
            "sanic": "sanic",
            "litestar": "litestar",
            "typer": "typer",
            "click": "click",
            "celery": "celery",
            "sqlalchemy": "sqlalchemy",
            "pydantic": "pydantic",
        }
        content_lower = content.lower()
        for marker, framework in framework_markers.items():
            if marker in content_lower and framework not in profile.frameworks:
                profile.frameworks.append(framework)

    def _detect_js_frameworks(self, deps: dict[str, str], profile: CodebaseProfile) -> None:
        framework_map = {
            "react": "react",
            "next": "next",
            "vue": "vue",
            "nuxt": "nuxt",
            "@angular/core": "angular",
            "svelte": "svelte",
            "@sveltejs/kit": "sveltekit",
            "express": "express",
            "fastify": "fastify",
            "koa": "koa",
            "hono": "hono",
            "nestjs": "nestjs",
            "@nestjs/core": "nestjs",
            "remix": "remix",
            "@remix-run/react": "remix",
            "gatsby": "gatsby",
            "astro": "astro",
            "electron": "electron",
            "tailwindcss": "tailwind",
            "prisma": "prisma",
            "@prisma/client": "prisma",
            "drizzle-orm": "drizzle",
        }
        for dep, framework in framework_map.items():
            if dep in deps and framework not in profile.frameworks:
                profile.frameworks.append(framework)

    # ------------------------------------------------------------------
    # Test frameworks
    # ------------------------------------------------------------------

    def _detect_test_frameworks(self, profile: CodebaseProfile) -> None:
        # Python
        if "python" in profile.languages:
            pyproject = self.workspace / "pyproject.toml"
            if pyproject.exists():
                try:
                    content = pyproject.read_text(errors="replace")
                    if "pytest" in content:
                        profile.test_frameworks.append("pytest")
                    if "unittest" in content:
                        profile.test_frameworks.append("unittest")
                except OSError:
                    pass
            # Check for test dirs as a fallback signal for pytest
            if not profile.test_frameworks:
                for d in ("tests", "test"):
                    if (self.workspace / d).is_dir():
                        profile.test_frameworks.append("pytest")
                        break

        # JS/TS
        pkg_json = self.workspace / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(errors="replace"))
                deps = {}
                deps.update(pkg.get("dependencies", {}))
                deps.update(pkg.get("devDependencies", {}))
                if "jest" in deps:
                    profile.test_frameworks.append("jest")
                if "vitest" in deps:
                    profile.test_frameworks.append("vitest")
                if "mocha" in deps:
                    profile.test_frameworks.append("mocha")
                if "@playwright/test" in deps:
                    profile.test_frameworks.append("playwright")
                if "cypress" in deps:
                    profile.test_frameworks.append("cypress")
            except (OSError, json.JSONDecodeError):
                pass

        # Go
        if "go" in profile.languages:
            profile.test_frameworks.append("go test")

        # Rust
        if "rust" in profile.languages:
            profile.test_frameworks.append("cargo test")

        profile.test_frameworks = list(dict.fromkeys(profile.test_frameworks))

    # ------------------------------------------------------------------
    # Command detection
    # ------------------------------------------------------------------

    def _detect_commands(self, profile: CodebaseProfile) -> None:
        lang = profile.primary_language

        # Try to detect from package.json scripts first
        pkg_json = self.workspace / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(errors="replace"))
                scripts = pkg.get("scripts", {})
                if "test" in scripts:
                    profile.test_command = profile.test_command or f"npm test"
                if "lint" in scripts:
                    profile.lint_command = profile.lint_command or "npm run lint"
                if "format" in scripts:
                    profile.format_command = profile.format_command or "npm run format"
                if "build" in scripts:
                    profile.build_command = profile.build_command or "npm run build"
                if "typecheck" in scripts or "type-check" in scripts:
                    profile.type_check_command = profile.type_check_command or "npm run typecheck"
                if "dev" in scripts:
                    profile.dev_server_command = profile.dev_server_command or "npm run dev"
                elif "start" in scripts:
                    profile.dev_server_command = profile.dev_server_command or "npm start"
            except (OSError, json.JSONDecodeError):
                pass

        # Python-specific commands
        if lang == "python":
            if "pytest" in profile.test_frameworks:
                profile.test_command = profile.test_command or "pytest"
            elif "unittest" in profile.test_frameworks:
                profile.test_command = profile.test_command or "python -m unittest discover"

            # Detect linter from config
            pyproject = self.workspace / "pyproject.toml"
            has_ruff = (
                "ruff.toml" in profile.config_files
                or (pyproject.exists() and "ruff" in pyproject.read_text(errors="replace"))
            )
            if has_ruff:
                profile.lint_command = profile.lint_command or "ruff check ."
                profile.format_command = profile.format_command or "ruff format ."
            elif ".flake8" in profile.config_files:
                profile.lint_command = profile.lint_command or "flake8"
            if not profile.format_command:
                # Check for black
                if pyproject.exists() and "black" in pyproject.read_text(errors="replace"):
                    profile.format_command = "black ."

            # Type checking
            if any(
                f in profile.config_files
                for f in ("mypy.ini", ".mypy.ini")
            ) or (pyproject.exists() and "mypy" in pyproject.read_text(errors="replace")):
                profile.type_check_command = profile.type_check_command or "mypy ."
            # Check for pyright
            if (self.workspace / "pyrightconfig.json").exists():
                profile.type_check_command = profile.type_check_command or "pyright"

            # Dev server
            if "django" in profile.frameworks and (self.workspace / "manage.py").exists():
                profile.dev_server_command = profile.dev_server_command or "python manage.py runserver"
            elif "flask" in profile.frameworks:
                profile.dev_server_command = profile.dev_server_command or "flask run"
            elif "fastapi" in profile.frameworks:
                profile.dev_server_command = profile.dev_server_command or "uvicorn app:app --reload"

        # TypeScript type checking
        if lang in ("typescript", "javascript") and "tsconfig.json" in profile.config_files:
            profile.type_check_command = profile.type_check_command or "npx tsc --noEmit"

        # Go
        if lang == "go":
            profile.test_command = profile.test_command or "go test ./..."
            profile.build_command = profile.build_command or "go build ./..."
            profile.lint_command = profile.lint_command or "golangci-lint run"
            profile.format_command = profile.format_command or "gofmt -w ."

        # Rust
        if lang == "rust":
            profile.test_command = profile.test_command or "cargo test"
            profile.build_command = profile.build_command or "cargo build"
            profile.lint_command = profile.lint_command or "cargo clippy"
            profile.format_command = profile.format_command or "cargo fmt"

    # ------------------------------------------------------------------
    # Project type classification
    # ------------------------------------------------------------------

    def _classify_project_type(self, profile: CodebaseProfile) -> None:
        web_frameworks = {
            "react", "next", "vue", "nuxt", "angular", "svelte", "sveltekit",
            "gatsby", "remix", "astro",
        }
        api_frameworks = {
            "flask", "django", "fastapi", "express", "fastify", "koa", "hono",
            "nestjs", "actix-web", "axum", "rocket", "gin", "echo", "chi",
            "starlette", "litestar", "sanic", "aiohttp", "tornado",
        }
        cli_frameworks = {"click", "typer", "cobra", "clap"}

        fw_set = set(profile.frameworks)

        profile.web_app = bool(fw_set & web_frameworks)
        profile.api_app = bool(fw_set & api_frameworks)
        profile.cli_app = bool(fw_set & cli_frameworks)

        # Library detection: has no server/web/CLI framework but has package config
        if not (profile.web_app or profile.api_app or profile.cli_app):
            if profile.package_managers:
                profile.library = True

        # A project with both web and API frameworks is both
        # Django/Next can be both web and API
        if "django" in fw_set or "next" in fw_set:
            profile.web_app = True
            profile.api_app = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _walk_files(self) -> list[Path]:
        """Walk the workspace, skipping ignored directories. Returns file paths."""
        files: list[Path] = []
        stack = [self.workspace]
        while stack:
            current = stack.pop()
            try:
                children = sorted(current.iterdir())
            except PermissionError:
                continue
            for child in children:
                if child.name in _IGNORE_DIRS or (
                    child.name.startswith(".") and child.is_dir()
                ):
                    continue
                if child.is_dir():
                    stack.append(child)
                elif child.is_file():
                    files.append(child)
        return files
