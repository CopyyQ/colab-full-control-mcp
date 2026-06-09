from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .artifact_tools import ArtifactTools
from .audit import AuditLogger
from .auth import AuthManager
from .code_tools import CodeTools
from .drive_tools import DriveTools
from .file_tools import FileTools
from .git_tools import GitTools
from .job_manager import JobManager
from .model_tools import ModelTools
from .notebook_tools import NotebookTools, PythonSessionManager
from .path_manager import PathManager
from .permissions import PermissionManager
from .python_tools import PythonTools
from .runtime_tools import RuntimeTools
from .settings import Settings
from .shell_tools import ShellTools


@dataclass(slots=True)
class ToolBundle:
    settings: Settings
    path_manager: PathManager
    auth_manager: AuthManager
    permission_manager: PermissionManager
    audit_logger: AuditLogger
    job_manager: JobManager
    session_manager: PythonSessionManager
    file_tools: FileTools
    code_tools: CodeTools
    shell_tools: ShellTools
    python_tools: PythonTools
    notebook_tools: NotebookTools
    git_tools: GitTools
    runtime_tools: RuntimeTools
    model_tools: ModelTools
    drive_tools: DriveTools
    artifact_tools: ArtifactTools


TOOL_REGISTRY: dict[str, list[str]] = {
    "file_tools": [
        "list_files",
        "list_tree",
        "read_file",
        "read_files",
        "read_binary_metadata",
        "get_file_info",
        "create_file",
        "write_file",
        "append_file",
        "patch_file",
        "replace_text",
        "copy_path",
        "move_path",
        "rename_path",
        "delete_path",
        "create_directory",
        "calculate_hash",
        "apply_unified_diff",
        "multi_file_patch",
    ],
    "code_tools": ["search_code", "read_project", "format_code"],
    "shell_tools": ["run_safe_command", "run_shell_command"],
    "python_tools": [
        "run_python_code",
        "run_python_file",
        "run_python_module",
        "run_pytest",
        "run_unit_test",
        "run_import_check",
        "run_compile_check",
        "install_python_packages",
        "uninstall_python_packages",
        "list_installed_packages",
        "check_package_version",
        "install_requirements",
    ],
    "notebook_tools": [
        "list_notebook_cells",
        "read_notebook",
        "read_notebook_cell",
        "update_notebook_cell",
        "insert_notebook_cell",
        "append_notebook_cell",
        "move_notebook_cell",
        "delete_notebook_cell",
        "clear_notebook_outputs",
        "set_notebook_metadata",
        "run_notebook",
        "run_notebook_cell",
        "export_notebook_to_python",
        "convert_python_to_notebook",
        "duplicate_notebook",
        "create_python_session",
        "execute_in_session",
        "get_session_variables",
        "list_session_variables",
        "delete_session_variable",
        "interrupt_session",
        "restart_session",
        "close_session",
        "list_sessions",
        "get_session_status",
        "get_session_output",
    ],
    "git_tools": [
        "git_status",
        "git_diff",
        "git_log",
        "git_branch",
        "git_checkout",
        "git_create_branch",
        "git_add",
        "git_commit",
        "git_pull",
        "git_push",
        "git_clone",
        "git_fetch",
        "git_merge",
        "git_stash",
        "git_restore",
    ],
    "runtime_tools": [
        "get_runtime_status",
        "get_gpu_status",
        "get_cpu_status",
        "get_memory_status",
        "get_disk_status",
        "get_process_list",
        "get_network_status",
        "get_cuda_status",
        "get_pytorch_status",
        "get_colab_status",
        "clear_cuda_cache",
        "garbage_collect",
        "terminate_managed_process",
        "restart_mcp_server",
    ],
    "model_tools": [
        "execute_project_task",
        "start_job",
        "start_python_job",
        "start_training_job",
        "resume_training_job",
        "start_notebook_job",
        "get_job_status",
        "get_job_logs",
        "stream_job_logs",
        "list_jobs",
        "stop_job",
        "restart_job",
        "wait_for_job",
        "delete_job_record",
        "run_validation_job",
        "run_inference_job",
        "run_benchmark_job",
        "export_model_job",
        "get_training_progress",
        "read_metrics",
        "compare_metrics",
        "list_checkpoints",
        "find_best_checkpoint",
        "get_checkpoint_info",
        "copy_checkpoint",
        "delete_checkpoint",
        "export_checkpoint",
        "count_parameters",
        "inspect_model",
        "measure_gpu_memory",
    ],
    "drive_tools": [
        "is_drive_mounted",
        "mount_drive_status",
        "list_drive_files",
        "read_drive_file",
        "copy_to_drive",
        "copy_from_drive",
        "sync_project_to_drive",
        "sync_project_from_drive",
        "backup_project",
        "backup_checkpoints",
        "delete_drive_path",
    ],
    "artifact_tools": [
        "list_artifacts",
        "get_artifact_info",
        "read_csv",
        "read_json",
        "read_yaml",
        "inspect_image",
        "save_plot",
        "create_archive",
        "extract_archive",
    ],
}


def build_tool_bundle(settings: Settings | None = None) -> ToolBundle:
    settings = settings or Settings()
    path_manager = PathManager(settings.allowed_root_paths(), settings.unrestricted_runtime_mode)
    auth_manager = AuthManager(settings.colab_mcp_token)
    permission_manager = PermissionManager(settings.permission_profile)
    audit_logger = AuditLogger(settings.audit_log)
    job_manager = JobManager(settings.job_db, settings.job_root, max_output_chars=settings.max_text_output_chars)
    session_manager = PythonSessionManager(settings.session_root)

    shared = {
        "settings": settings,
        "auth_manager": auth_manager,
        "permission_manager": permission_manager,
        "audit_logger": audit_logger,
    }
    file_tools = FileTools(path_manager=path_manager, **shared)
    code_tools = CodeTools(path_manager=path_manager, **shared)
    shell_tools = ShellTools(path_manager=path_manager, job_manager=job_manager, **shared)
    python_tools = PythonTools(path_manager=path_manager, job_manager=job_manager, **shared)
    notebook_tools = NotebookTools(path_manager=path_manager, session_manager=session_manager, **shared)
    git_tools = GitTools(path_manager=path_manager, **shared)
    runtime_tools = RuntimeTools(job_manager=job_manager, **shared)
    model_tools = ModelTools(path_manager=path_manager, job_manager=job_manager, runtime_tools=runtime_tools, **shared)
    drive_tools = DriveTools(path_manager=path_manager, **shared)
    artifact_tools = ArtifactTools(path_manager=path_manager, **shared)

    return ToolBundle(
        settings=settings,
        path_manager=path_manager,
        auth_manager=auth_manager,
        permission_manager=permission_manager,
        audit_logger=audit_logger,
        job_manager=job_manager,
        session_manager=session_manager,
        file_tools=file_tools,
        code_tools=code_tools,
        shell_tools=shell_tools,
        python_tools=python_tools,
        notebook_tools=notebook_tools,
        git_tools=git_tools,
        runtime_tools=runtime_tools,
        model_tools=model_tools,
        drive_tools=drive_tools,
        artifact_tools=artifact_tools,
    )


def register_tools(mcp: Any, bundle: ToolBundle) -> None:
    for toolset_name, tool_names in TOOL_REGISTRY.items():
        toolset = getattr(bundle, toolset_name)
        for tool_name in tool_names:
            handler = getattr(toolset, tool_name)
            mcp.tool(name=tool_name, description=tool_name.replace("_", " "))(handler)
