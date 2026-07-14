from collections.abc import Sequence
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
import json
import os
from . import obsidian

api_key = os.getenv("OBSIDIAN_API_KEY", "")
obsidian_host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")

def get_active_vault_connection():
    """Returns (host, port, api_key, use_https, vault_path) for the active vault connection."""
    import os
    import json
    import platform
    
    # Defaults
    default_host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")
    default_key = os.getenv("OBSIDIAN_API_KEY", "")
    default_port = 27123
    use_https = False
    
    # 1. Determine active vault path from state file
    state_path = os.path.join(os.path.dirname(__file__), "../../.active_vault.json")
    active_path = None
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
                active_path = state.get("active_vault_path")
        except Exception:
            pass
            
    # 2. If no state, fall back to last active vault from obsidian.json
    if not active_path:
        json_path = None
        system = platform.system()
        if system == "Windows":
            appdata = os.environ.get("APPDATA")
            if appdata:
                json_path = os.path.join(appdata, "obsidian\\obsidian.json")
        elif system == "Darwin":
            json_path = os.path.expanduser("~/Library/Application Support/obsidian/obsidian.json")
        else:
            json_path = os.path.expanduser("~/.config/obsidian/obsidian.json")

        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    vaults = data.get("vaults", {})
                    for k, v in vaults.items():
                        if v.get("open"):
                            active_path = os.path.normpath(v.get("path"))
                            break
            except Exception:
                pass

    # 3. Read vault-specific settings (port and api key) from the active vault
    if active_path:
        # Check both Windows-style and Unix-style slashes
        settings_path = os.path.join(active_path, ".obsidian", "plugins", "obsidian-local-rest-api", "data.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    val_key = settings.get("apiKey", default_key)
                    
                    # Determine port based on secure/insecure settings
                    enable_insecure = settings.get("enableInsecureServer", True)
                    insecure_port = settings.get("insecurePort", 27123)
                    secure_port = settings.get("port", 27124)
                    
                    if enable_insecure:
                        return default_host, insecure_port, val_key, False, active_path
                    else:
                        return default_host, secure_port, val_key, True, active_path
            except Exception:
                pass
                
    return default_host, default_port, default_key, use_https, active_path

def get_obsidian_api() -> obsidian.Obsidian:
    host, port, key, use_https, vault_path = get_active_vault_connection()
    protocol = "https" if use_https else "http"
    if not key:
        raise ValueError("OBSIDIAN_API_KEY required. Please configure it in your vault settings or set OBSIDIAN_API_KEY in your .env file.")
    return obsidian.Obsidian(api_key=key, host=host, port=port, protocol=protocol)


TOOL_LIST_FILES_IN_VAULT = "obsidian_list_files_in_vault"
TOOL_LIST_FILES_IN_DIR = "obsidian_list_files_in_dir"

class ToolHandler():
    def __init__(self, tool_name: str):
        self.name = tool_name

    def get_tool_description(self) -> Tool:
        raise NotImplementedError()

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        raise NotImplementedError()
    
class ListFilesInVaultToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_LIST_FILES_IN_VAULT)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Lists all files and directories in the root directory of your Obsidian vault.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        api = get_obsidian_api()

        files = api.list_files_in_vault()

        return [
            TextContent(
                type="text",
                text=json.dumps(files, indent=2)
            )
        ]
    
class ListFilesInDirToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_LIST_FILES_IN_DIR)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Lists all files and directories that exist in a specific Obsidian directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dirpath": {
                        "type": "string",
                        "description": "Path to list files from (relative to your vault root). Note that empty directories will not be returned."
                    },
                },
                "required": ["dirpath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:

        if "dirpath" not in args:
            raise RuntimeError("dirpath argument missing in arguments")

        api = get_obsidian_api()

        files = api.list_files_in_dir(args["dirpath"])

        return [
            TextContent(
                type="text",
                text=json.dumps(files, indent=2)
            )
        ]
    
class GetFileContentsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_file_contents")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Return the content of a single file in your vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the relevant file (relative to your vault root).",
                        "format": "path"
                    },
                },
                "required": ["filepath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args:
            raise RuntimeError("filepath argument missing in arguments")

        api = get_obsidian_api()

        content = api.get_file_contents(args["filepath"])

        return [
            TextContent(
                type="text",
                text=json.dumps(content, indent=2)
            )
        ]
    
class SearchToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_simple_search")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="""Simple search for documents matching a specified text query across all files in the vault. 
            Use this tool when you want to do a simple text search""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to a simple search for in the vault."
                    },
                    "context_length": {
                        "type": "integer",
                        "description": "How much context to return around the matching string (default: 100)",
                        "default": 100
                    }
                },
                "required": ["query"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "query" not in args:
            raise RuntimeError("query argument missing in arguments")

        context_length = args.get("context_length", 100)
        
        api = get_obsidian_api()
        results = api.search(args["query"], context_length)
        
        formatted_results = []
        for result in results:
            formatted_matches = []
            for match in result.get('matches', []):
                context = match.get('context', '')
                match_pos = match.get('match', {})
                start = match_pos.get('start', 0)
                end = match_pos.get('end', 0)
                
                formatted_matches.append({
                    'context': context,
                    'match_position': {'start': start, 'end': end}
                })
                
            formatted_results.append({
                'filename': result.get('filename', ''),
                'score': result.get('score', 0),
                'matches': formatted_matches
            })

        return [
            TextContent(
                type="text",
                text=json.dumps(formatted_results, indent=2)
            )
        ]
    
class AppendContentToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_append_content")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description="Append content to a new or existing file in the vault.",
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file (relative to vault root)",
                       "format": "path"
                   },
                   "content": {
                       "type": "string",
                       "description": "Content to append to the file"
                   }
               },
               "required": ["filepath", "content"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args or "content" not in args:
           raise RuntimeError("filepath and content arguments required")

       api = get_obsidian_api()
       api.append_content(args.get("filepath", ""), args["content"])

       return [
           TextContent(
               type="text",
               text=f"Successfully appended content to {args['filepath']}"
           )
       ]
   
class PatchContentToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_patch_content")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description=(
               "Insert content into an existing note relative to a heading, block reference, "
               "or frontmatter field. For target_type='heading', target must be the fully "
               "qualified heading path joined with '::' (e.g. 'Outer::Inner'). Bare heading "
               "names (without '::') will be auto-qualified if they match exactly one heading "
               "in the file."
           ),
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file (relative to vault root)",
                       "format": "path"
                   },
                   "operation": {
                       "type": "string",
                       "description": "Operation to perform (append, prepend, or replace)",
                       "enum": ["append", "prepend", "replace"]
                   },
                   "target_type": {
                       "type": "string",
                       "description": "Type of target to patch",
                       "enum": ["heading", "block", "frontmatter"]
                   },
                   "target": {
                       "type": "string",
                       "description": (
                           "Target identifier. For target_type='heading': fully qualified "
                           "path with '::' delimiter, e.g. 'Section::Subsection'. Bare names "
                           "(no '::') are auto-qualified if unambiguous. For 'block': the "
                           "block reference id. For 'frontmatter': the YAML field name."
                       )
                   },
                   "content": {
                       "type": "string",
                       "description": "Content to insert"
                   }
               },
               "required": ["filepath", "operation", "target_type", "target", "content"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if not all(k in args for k in ["filepath", "operation", "target_type", "target", "content"]):
           raise RuntimeError("filepath, operation, target_type, target and content arguments required")

       api = get_obsidian_api()
       api.patch_content(
           args.get("filepath", ""),
           args.get("operation", ""),
           args.get("target_type", ""),
           args.get("target", ""),
           args.get("content", "")
       )

       return [
           TextContent(
               type="text",
               text=f"Successfully patched content in {args['filepath']}"
           )
       ]
       
class PutContentToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_put_content")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description=(
               "Creates a new file, or COMPLETELY OVERWRITES the content of an existing "
               "file. The previous content is lost. "
               "Use `obsidian_append_content` to add content to a file without erasing "
               "what's already there. Use `obsidian_patch_content` to modify a specific "
               "heading, block or frontmatter field while keeping the rest intact."
           ),
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the relevant file (relative to your vault root)",
                       "format": "path"
                   },
                   "content": {
                       "type": "string",
                       "description": "Full file content. Replaces existing content entirely if the file already exists."
                   }
               },
               "required": ["filepath", "content"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args or "content" not in args:
           raise RuntimeError("filepath and content arguments required")

       api = get_obsidian_api()
       api.put_content(args.get("filepath", ""), args["content"])

       return [
           TextContent(
               type="text",
               text=f"Successfully uploaded content to {args['filepath']}"
           )
       ]
   

class DeleteFileToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_delete_file")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description="Delete a file or directory from the vault.",
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file or directory to delete (relative to vault root)",
                       "format": "path"
                   },
                   "confirm": {
                       "type": "boolean",
                       "description": "Confirmation to delete the file (must be true)",
                       "default": False
                   }
               },
               "required": ["filepath", "confirm"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args:
           raise RuntimeError("filepath argument missing in arguments")
       
       if not args.get("confirm", False):
           raise RuntimeError("confirm must be set to true to delete a file")

       api = get_obsidian_api()
       api.delete_file(args["filepath"])

       return [
           TextContent(
               type="text",
               text=f"Successfully deleted {args['filepath']}"
           )
       ]
   
class ComplexSearchToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_complex_search")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description="""Complex search for documents using a JsonLogic query. 
           Supports standard JsonLogic operators plus 'glob' and 'regexp' for pattern matching. Results must be non-falsy.

           Use this tool when you want to do a complex search, e.g. for all documents with certain tags etc.
           ALWAYS follow query syntax in examples.

           Examples
            1. Match all markdown files
            {"glob": ["*.md", {"var": "path"}]}

            2. Match all markdown files with 1221 substring inside them
            {
              "and": [
                { "glob": ["*.md", {"var": "path"}] },
                { "regexp": [".*1221.*", {"var": "content"}] }
              ]
            }

            3. Match all markdown files in Work folder containing name Keaton
            {
              "and": [
                { "glob": ["*.md", {"var": "path"}] },
                { "regexp": [".*Work.*", {"var": "path"}] },
                { "regexp": ["Keaton", {"var": "content"}] }
              ]
            }
           """,
           inputSchema={
               "type": "object",
               "properties": {
                   "query": {
                       "type": "object",
                       "description": "JsonLogic query object. ALWAYS follow query syntax in examples. \
                            Example 1: {\"glob\": [\"*.md\", {\"var\": \"path\"}]} matches all markdown files \
                            Example 2: {\"and\": [{\"glob\": [\"*.md\", {\"var\": \"path\"}]}, {\"regexp\": [\".*1221.*\", {\"var\": \"content\"}]}]} matches all markdown files with 1221 substring inside them \
                            Example 3: {\"and\": [{\"glob\": [\"*.md\", {\"var\": \"path\"}]}, {\"regexp\": [\".*Work.*\", {\"var\": \"path\"}]}, {\"regexp\": [\"Keaton\", {\"var\": \"content\"}]}]} matches all markdown files in Work folder containing name Keaton \
                        "
                   }
               },
               "required": ["query"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "query" not in args:
           raise RuntimeError("query argument missing in arguments")

       api = get_obsidian_api()
       results = api.search_json(args.get("query", ""))

       return [
           TextContent(
               type="text",
               text=json.dumps(results, indent=2)
           )
       ]

class SearchByTagToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_search_by_tag")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description=(
               "Find all notes carrying a specific tag. Matches the note's parsed "
               "tag set (YAML frontmatter `tags:` plus inline `#tag` occurrences), "
               "so hits on the tag name inside ordinary prose are NOT returned. "
               "Pass the tag without the leading '#'. Hierarchical-tag matching is "
               "exact — searching for 'work' will not match notes tagged "
               "'work/tasks'. Optionally scope to a vault subdirectory."
           ),
           inputSchema={
               "type": "object",
               "properties": {
                   "tag": {
                       "type": "string",
                       "description": "Tag name without the leading '#' (e.g. 'project', 'work/tasks')."
                   },
                   "dirpath": {
                       "type": "string",
                       "description": "Optional vault-relative directory to scope results to (e.g. 'work/projects'). Trailing slash is stripped."
                   }
               },
               "required": ["tag"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "tag" not in args:
           raise RuntimeError("tag argument missing in arguments")

       api = get_obsidian_api()
       paths = api.search_by_tag(args["tag"], args.get("dirpath"))

       return [
           TextContent(
               type="text",
               text=json.dumps(paths, indent=2)
           )
       ]


class GetFrontmatterToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_get_frontmatter")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description=(
               "Return just the YAML frontmatter of a note as a parsed JSON "
               "object. Lighter than obsidian_get_file_contents when you only "
               "need metadata (tags, aliases, status fields, etc.). Returns "
               "an empty object for notes without frontmatter."
           ),
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file (relative to vault root)",
                       "format": "path"
                   }
               },
               "required": ["filepath"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args:
           raise RuntimeError("filepath argument missing in arguments")

       api = get_obsidian_api()
       fm = api.get_frontmatter(args["filepath"])

       return [
           TextContent(
               type="text",
               text=json.dumps(fm, indent=2)
           )
       ]


class BatchGetFileContentsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_batch_get_file_contents")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Return the contents of multiple files in your vault, concatenated with headers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepaths": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "Path to a file (relative to your vault root)",
                            "format": "path"
                        },
                        "description": "List of file paths to read"
                    },
                },
                "required": ["filepaths"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepaths" not in args:
            raise RuntimeError("filepaths argument missing in arguments")

        api = get_obsidian_api()
        content = api.get_batch_file_contents(args["filepaths"])

        return [
            TextContent(
                type="text",
                text=content
            )
        ]

class PeriodicNotesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_periodic_note")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get current periodic note for the specified period.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "The period type (daily, weekly, monthly, quarterly, yearly)",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"]
                    },
                    "type": {
                        "type": "string",
                        "description": "The type of data to get ('content' or 'metadata'). 'content' returns just the content in Markdown format. 'metadata' includes note metadata (including paths, tags, etc.) and the content.",
                        "default": "content",
                        "enum": ["content", "metadata"]
                    }
                },
                "required": ["period"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "period" not in args:
            raise RuntimeError("period argument missing in arguments")

        period = args["period"]
        valid_periods = ["daily", "weekly", "monthly", "quarterly", "yearly"]
        if period not in valid_periods:
            raise RuntimeError(f"Invalid period: {period}. Must be one of: {', '.join(valid_periods)}")
        
        type = args["type"] if "type" in args else "content"
        valid_types = ["content", "metadata"]
        if type not in valid_types:
            raise RuntimeError(f"Invalid type: {type}. Must be one of: {', '.join(valid_types)}")

        api = get_obsidian_api()
        content = api.get_periodic_note(period,type)

        return [
            TextContent(
                type="text",
                text=content
            )
        ]
        
class RecentPeriodicNotesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_recent_periodic_notes")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get most recent periodic notes for the specified period type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "The period type (daily, weekly, monthly, quarterly, yearly)",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of notes to return (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Whether to include note content (default: false)",
                        "default": False
                    }
                },
                "required": ["period"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "period" not in args:
            raise RuntimeError("period argument missing in arguments")

        period = args["period"]
        valid_periods = ["daily", "weekly", "monthly", "quarterly", "yearly"]
        if period not in valid_periods:
            raise RuntimeError(f"Invalid period: {period}. Must be one of: {', '.join(valid_periods)}")

        limit = args.get("limit", 5)
        if not isinstance(limit, int) or limit < 1:
            raise RuntimeError(f"Invalid limit: {limit}. Must be a positive integer")
            
        include_content = args.get("include_content", False)
        if not isinstance(include_content, bool):
            raise RuntimeError(f"Invalid include_content: {include_content}. Must be a boolean")

        api = get_obsidian_api()
        results = api.get_recent_periodic_notes(period, limit, include_content)

        return [
            TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )
        ]
        
class RecentChangesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_recent_changes")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get recently modified files in the vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of files to return (default: 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100
                    },
                    "days": {
                        "type": "integer",
                        "description": "Only include files modified within this many days (default: 90)",
                        "minimum": 1,
                        "default": 90
                    }
                }
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        limit = args.get("limit", 10)
        if not isinstance(limit, int) or limit < 1:
            raise RuntimeError(f"Invalid limit: {limit}. Must be a positive integer")
            
        days = args.get("days", 90)
        if not isinstance(days, int) or days < 1:
            raise RuntimeError(f"Invalid days: {days}. Must be a positive integer")

        api = get_obsidian_api()
        results = api.get_recent_changes(limit, days)

        return [
            TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )
        ]

class WakeUpObsidianToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_wake_up")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Checks if Obsidian is running, lists available vaults, and launches a specific vault (or the last open one). Handles switching between vaults.",
            inputSchema={
                "type": "object",
                "properties": {
                    "vault_path": {
                        "type": "string",
                        "description": "Optional absolute path of the vault to open (e.g. 'C:\\Users\\conta\\Documents\\Vault'). If omitted, opens the last active vault."
                    }
                },
                "required": []
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        import os
        import platform
        import json
        import subprocess
        import urllib.parse
        import requests

        system = platform.system()
        vaults_info = {}
        last_open_vault = None
        
        # 1. Parse obsidian.json to find available vaults
        json_path = None
        if system == "Windows":
            appdata = os.environ.get("APPDATA")
            if appdata:
                json_path = os.path.join(appdata, "obsidian\\obsidian.json")
        elif system == "Darwin":
            json_path = os.path.expanduser("~/Library/Application Support/obsidian/obsidian.json")
        else:
            json_path = os.path.expanduser("~/.config/obsidian/obsidian.json")

        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    vaults = data.get("vaults", {})
                    for k, v in vaults.items():
                        v_path = v.get("path")
                        if v_path:
                            v_path_norm = os.path.normpath(v_path)
                            vaults_info[k] = v_path_norm
                            if v.get("open"):
                                last_open_vault = v_path_norm
            except Exception:
                pass

        # 2. Determine target vault to open
        target_path = args.get("vault_path")
        if target_path:
            target_path = os.path.normpath(target_path)
        else:
            target_path = last_open_vault

        # 3. Save target_path to state file
        if target_path:
            state_path = os.path.join(os.path.dirname(__file__), "../../.active_vault.json")
            try:
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump({"active_vault_path": target_path}, f)
            except Exception:
                pass

        # 4. Resolve host, port, API key for this target vault
        host, port, key, use_https, resolved_path = get_active_vault_connection()
        
        # 5. Check if this specific vault's REST API is currently active
        is_running = False
        try:
            proto = "https" if use_https else "http"
            url = f"{proto}://{host}:{port}/"
            headers = {"Authorization": f"Bearer {key}"}
            r = requests.get(url, headers=headers, timeout=1.5, verify=False)
            if r.status_code == 200:
                is_running = True
        except Exception:
            is_running = False

        # 6. Launch the vault if it is not already running
        launched = False
        error_msg = ""
        launch_url = "obsidian://open"
        if target_path:
            encoded_path = urllib.parse.quote(target_path)
            launch_url = f"obsidian://open?path={encoded_path}"

        if not is_running:
            if system == "Windows":
                # If no specific vault is targeted, try launching the executable directly
                if not target_path:
                    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
                    local_appdata = os.environ.get("LocalAppData", "")
                    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                    
                    paths = []
                    if local_appdata:
                        paths.append(os.path.join(local_appdata, "Obsidian\\Obsidian.exe"))
                    paths.append(os.path.join(program_files, "Obsidian\\Obsidian.exe"))
                    paths.append(os.path.join(program_files_x86, "Obsidian\\Obsidian.exe"))

                    for path in paths:
                        if os.path.exists(path):
                            try:
                                cmd = ["powershell.exe", "-Command", f"Start-Process '{path}' -Wait"]
                                subprocess.Popen(cmd)
                                launched = True
                                break
                            except Exception as e:
                                error_msg = str(e)

                if not launched:
                    try:
                        cmd = ["powershell.exe", "-Command", f"Start-Process '{launch_url}' -Wait"]
                        subprocess.Popen(cmd)
                        launched = True
                    except Exception as e:
                        error_msg = str(e)

            elif system == "Darwin":  # macOS
                try:
                    if target_path:
                        subprocess.Popen(["open", launch_url])
                    else:
                        macos_path = "/Applications/Obsidian.app"
                        if os.path.exists(macos_path):
                            subprocess.Popen(["open", macos_path])
                        else:
                            subprocess.Popen(["open", launch_url])
                    launched = True
                except Exception as e:
                    error_msg = str(e)

            else:  # Linux / other
                try:
                    if target_path:
                        subprocess.Popen(["xdg-open", launch_url])
                    else:
                        try:
                            subprocess.Popen(["obsidian"])
                        except Exception:
                            subprocess.Popen(["xdg-open", launch_url])
                    launched = True
                except Exception as e:
                    error_msg = str(e)

        # 7. Format results
        status_text = "running" if (is_running or launched) else "not running"
        active_vault_text = f"listening on port {port}" if is_running else "not responding on port"
        
        response_msg = f"Obsidian status: {status_text} (Vault '{target_path}' {active_vault_text}).\n"
        if launched:
            response_msg += f"Successfully triggered launch command for vault: '{target_path}'.\n"
        elif is_running:
            response_msg += f"Vault is already running and accessible on port {port}.\n"
        else:
            response_msg += f"Failed to trigger launch command: {error_msg}.\n"

        if vaults_info:
            response_msg += "\nDetected vaults on system:\n"
            for k, path in vaults_info.items():
                marker = ""
                if path == target_path:
                    marker = " [Selected / Active]"
                response_msg += f"- {path}{marker}\n"
        else:
            response_msg += "\nNo registered vaults detected in system configuration."

        return [
            TextContent(
                type="text",
                text=response_msg
            )
        ]








