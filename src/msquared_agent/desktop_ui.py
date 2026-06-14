import json
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from msquared_agent.agent import generate_draft
from msquared_agent.approval_queue import approve_item, list_queue, reject_item
from msquared_agent.app_log import APP_LOG_FILE, log_event, read_log_events
from msquared_agent.audit_store import AUDIT_FILE, read_audit_records
from msquared_agent.connector_config import connector_status, email_connector_config, x_connector_config
from msquared_agent.env_loader import DEFAULT_OPENAI_MODEL, read_env_values, save_env_values
from msquared_agent.email_adapter import fetch_inbound_emails, prepare_email_payload, send_approved_email
from msquared_agent.interactive_agent import agent_status, ask_agent, create_agent_draft, summarize_context
from msquared_agent.intake_store import add_intake_item, list_intake, update_intake_status
from msquared_agent.paths import app_root
from msquared_agent.product_knowledge import build_product_knowledge_index, build_validation_packet, knowledge_status
from msquared_agent.settings import DEFAULT_FEATURE_FLAGS, load_feature_flags, save_feature_flags
from msquared_agent.x_adapter import fetch_x_feed, post_approved_tweet, prepare_x_payload, test_x_connection


class MSquaredDesktopApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MSquared Operator Console")
        self.geometry("1180x760")
        self.minsize(780, 520)

        self.status_text = tk.StringVar(value="Ready. Human approval is required before any post or send.")
        self.intake_filter = tk.StringVar(value="all")
        self.intake_channel_filter = tk.StringVar(value="all")
        self.queue_filter = tk.StringVar(value="drafted")
        self.queue_channel_filter = tk.StringVar(value="all")
        self.composer_type = tk.StringVar(value="x_post")
        self.agent_draft_type = tk.StringVar(value="x_post")
        self.agent_context_source = tk.StringVar(value="auto")
        self.agent_knowledge_mode = tk.StringVar(value="public_safe")
        self.manual_channel = tk.StringVar(value="x")
        self.manual_source_type = tk.StringVar(value="x_mention")
        self.selected_intake_id = None
        self.selected_item_id = None
        self.intake_items = []
        self.queue_items = []
        self.admin_vars = {}
        self.admin_flag_vars = {}
        self.secret_entries = []
        self.show_secrets = tk.BooleanVar(value=False)
        self.prepared_payload_item_id = None
        self.agent_messages = []
        self.agent_busy = False
        self.knowledge_busy = False

        self._configure_style()
        self._build_layout()
        self.refresh_intake()
        self.refresh_queue()
        self.refresh_diagnostics()

    def _configure_style(self):
        self.configure(bg="#f5f6f8")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f5f6f8")
        style.configure("Panel.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        style.configure("TLabel", background="#f5f6f8", foreground="#172033", font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background="#ffffff", foreground="#172033", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#f5f6f8", foreground="#172033", font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background="#f5f6f8", foreground="#5d6876", font=("Segoe UI", 10))
        style.configure("Status.TLabel", background="#e8edf3", foreground="#213047", font=("Segoe UI", 9))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _make_scrollable_frame(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        canvas = tk.Canvas(parent, bg="#f5f6f8", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", fit_content_width)
        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))
        return content

    def _build_layout(self):
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="MSquared Operator Console", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="Monitor X and website email intake, draft as MSquared, approve, then prepare or execute guarded actions.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        monitor_tab = ttk.Frame(self.tabs, padding=10)
        agent_tab = ttk.Frame(self.tabs, padding=10)
        composer_tab = ttk.Frame(self.tabs, padding=10)
        approval_tab = ttk.Frame(self.tabs, padding=10)
        settings_tab = ttk.Frame(self.tabs, padding=10)
        diagnostics_tab = ttk.Frame(self.tabs, padding=10)
        self.approval_tab = approval_tab
        self.tabs.add(monitor_tab, text="Monitor")
        self.tabs.add(agent_tab, text="Agent")
        self.tabs.add(composer_tab, text="Composer")
        self.tabs.add(approval_tab, text="Approval")
        self.tabs.add(settings_tab, text="Settings")
        self.tabs.add(diagnostics_tab, text="Diagnostics")

        self._build_monitor_tab(monitor_tab)
        self._build_agent_tab(agent_tab)
        self._build_composer_tab(composer_tab)
        self._build_approval_tab(approval_tab)
        self._build_settings_tab(settings_tab)
        self._build_diagnostics_tab(diagnostics_tab)

        footer = ttk.Frame(outer)
        footer.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(footer, textvariable=self.status_text, style="Status.TLabel", padding=(8, 5)).pack(fill=tk.X)

    def _build_monitor_tab(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="Refresh X", command=self.refresh_x).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Refresh Email", command=self.refresh_email).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Refresh All", command=self.refresh_all_sources).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(toolbar, text="Status").pack(side=tk.LEFT, padx=(18, 6))
        filter_picker = ttk.Combobox(
            toolbar,
            textvariable=self.intake_filter,
            values=("all", "new", "drafted", "archived"),
            width=12,
            state="readonly",
        )
        filter_picker.pack(side=tk.LEFT)
        filter_picker.bind("<<ComboboxSelected>>", lambda _event: self.refresh_intake())
        ttk.Label(toolbar, text="Channel").pack(side=tk.LEFT, padx=(12, 6))
        channel_picker = ttk.Combobox(
            toolbar,
            textvariable=self.intake_channel_filter,
            values=("all", "x", "email"),
            width=10,
            state="readonly",
        )
        channel_picker.pack(side=tk.LEFT)
        channel_picker.bind("<<ComboboxSelected>>", lambda _event: self.refresh_intake())

        table_frame = ttk.Frame(parent, style="Panel.TFrame", padding=8)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("id", "channel", "source", "from", "subject", "status")
        self.intake_table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {"id": "ID", "channel": "Channel", "source": "Source", "from": "From", "subject": "Subject/Text", "status": "Status"}
        widths = {"id": 70, "channel": 75, "source": 120, "from": 140, "subject": 320, "status": 80}
        for column in columns:
            self.intake_table.heading(column, text=headings[column])
            self.intake_table.column(column, width=widths[column], minwidth=60, stretch=column == "subject")
        self.intake_table.grid(row=0, column=0, sticky="nsew")
        intake_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.intake_table.yview)
        intake_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.intake_table.xview)
        self.intake_table.configure(yscrollcommand=intake_scroll_y.set, xscrollcommand=intake_scroll_x.set)
        intake_scroll_y.grid(row=0, column=1, sticky="ns")
        intake_scroll_x.grid(row=1, column=0, sticky="ew")
        self.intake_table.bind("<<TreeviewSelect>>", self.on_intake_select)

        detail = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        detail.grid(row=1, column=1, sticky="nsew")
        detail.rowconfigure(3, weight=1)
        detail.columnconfigure(0, weight=1)

        ttk.Label(detail, text="Selected Intake", style="Panel.TLabel", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.intake_meta = ttk.Label(detail, text="No intake selected.", style="Panel.TLabel", foreground="#405166")
        self.intake_meta.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        self.intake_preview = tk.Text(detail, height=12, wrap=tk.WORD, font=("Segoe UI", 10), state=tk.DISABLED)
        self.intake_preview.grid(row=3, column=0, sticky="nsew")

        action_row = ttk.Frame(detail, style="Panel.TFrame")
        action_row.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(action_row, text="Draft X Reply", command=lambda: self.draft_from_intake("x_reply")).pack(side=tk.LEFT)
        ttk.Button(action_row, text="Draft X Post", command=lambda: self.draft_from_intake("x_post")).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(action_row, text="Draft Email", command=lambda: self.draft_from_intake("email_response")).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(action_row, text="Archive", command=self.archive_selected_intake).pack(side=tk.RIGHT)

        manual = ttk.LabelFrame(parent, text="Add Manual Intake", padding=10)
        manual.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        manual.columnconfigure(5, weight=1)
        ttk.Label(manual, text="Channel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(manual, textvariable=self.manual_channel, values=("x", "email"), width=8, state="readonly").grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Label(manual, text="Source").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            manual,
            textvariable=self.manual_source_type,
            values=("x_mention", "x_reply", "x_monitor", "keyword_search", "website_contact"),
            width=16,
            state="readonly",
        ).grid(row=0, column=3, sticky="w", padx=(6, 12))
        ttk.Label(manual, text="From").grid(row=0, column=4, sticky="w")
        self.manual_from = ttk.Entry(manual)
        self.manual_from.grid(row=0, column=5, sticky="ew", padx=(6, 0))
        ttk.Label(manual, text="Subject").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.manual_subject = ttk.Entry(manual)
        self.manual_subject.grid(row=1, column=1, columnspan=5, sticky="ew", padx=(6, 0), pady=(8, 0))
        self.manual_text = tk.Text(manual, height=3, wrap=tk.WORD, font=("Segoe UI", 10))
        self.manual_text.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        ttk.Button(manual, text="Add Intake", command=self.add_manual_intake).grid(row=3, column=5, sticky="e", pady=(8, 0))

    def _build_agent_tab(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(toolbar, text="MSquared Agent", font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        self.agent_status_label = ttk.Label(toolbar, text="", foreground="#405166")
        self.agent_status_label.pack(side=tk.LEFT, padx=(14, 0))
        ttk.Button(toolbar, text="Refresh Context", command=self.refresh_agent_context).pack(side=tk.RIGHT)
        ttk.Button(toolbar, text="Clear Chat", command=self.clear_agent_chat).pack(side=tk.RIGHT, padx=(0, 8))

        chat_frame = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        chat_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)
        self.agent_transcript = tk.Text(chat_frame, wrap=tk.WORD, font=("Segoe UI", 10), state=tk.DISABLED)
        self.agent_transcript.grid(row=0, column=0, sticky="nsew")
        transcript_scroll = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self.agent_transcript.yview)
        self.agent_transcript.configure(yscrollcommand=transcript_scroll.set)
        transcript_scroll.grid(row=0, column=1, sticky="ns")

        prompt_frame = ttk.Frame(chat_frame, style="Panel.TFrame")
        prompt_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        prompt_frame.columnconfigure(0, weight=1)
        self.agent_prompt = tk.Text(prompt_frame, height=4, wrap=tk.WORD, font=("Segoe UI", 10), undo=True)
        self.agent_prompt.grid(row=0, column=0, sticky="ew")
        self.agent_ask_button = ttk.Button(prompt_frame, text="Ask", style="Accent.TButton", command=self.ask_agent_async)
        self.agent_ask_button.grid(row=0, column=1, sticky="ns", padx=(8, 0))

        side = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        side.grid(row=1, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(2, weight=1)
        ttk.Label(side, text="Selected Context", style="Panel.TLabel", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        context_controls = ttk.Frame(side, style="Panel.TFrame")
        context_controls.grid(row=1, column=0, sticky="ew", pady=(8, 6))
        ttk.Label(context_controls, text="Use", style="Panel.TLabel").pack(side=tk.LEFT)
        context_picker = ttk.Combobox(
            context_controls,
            textvariable=self.agent_context_source,
            values=("auto", "selected_intake", "selected_draft", "none"),
            width=16,
            state="readonly",
        )
        context_picker.pack(side=tk.LEFT, padx=(8, 0))
        context_picker.bind("<<ComboboxSelected>>", lambda _event: self.refresh_agent_context())

        self.agent_context_box = tk.Text(side, height=8, wrap=tk.WORD, font=("Segoe UI", 9), state=tk.DISABLED)
        self.agent_context_box.grid(row=2, column=0, sticky="nsew")

        draft_box = ttk.LabelFrame(side, text="Create Draft", padding=10)
        draft_box.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        draft_box.columnconfigure(1, weight=1)
        ttk.Label(draft_box, text="Type").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            draft_box,
            textvariable=self.agent_draft_type,
            values=("x_post", "x_reply", "email_response"),
            width=16,
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(draft_box, text="Create Approval Draft", command=self.create_agent_draft_from_prompt).grid(row=1, column=1, sticky="e", pady=(8, 0))

        knowledge_box = ttk.LabelFrame(side, text="Product Knowledge", padding=10)
        knowledge_box.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        knowledge_box.columnconfigure(1, weight=1)
        ttk.Label(knowledge_box, text="Mode").grid(row=0, column=0, sticky="w")
        knowledge_picker = ttk.Combobox(
            knowledge_box,
            textvariable=self.agent_knowledge_mode,
            values=("public_safe", "technical_local", "technical_openai"),
            width=18,
            state="readonly",
        )
        knowledge_picker.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.knowledge_status_label = ttk.Label(knowledge_box, text="", wraplength=430)
        self.knowledge_status_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        knowledge_actions = ttk.Frame(knowledge_box)
        knowledge_actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.refresh_knowledge_button = ttk.Button(knowledge_actions, text="Refresh Product Knowledge", command=self.refresh_product_knowledge_async)
        self.refresh_knowledge_button.pack(side=tk.LEFT)
        ttk.Button(knowledge_actions, text="Copy Validation Packet", command=self.copy_validation_packet).pack(side=tk.LEFT, padx=(8, 0))

        self._update_agent_status_label()
        self._update_knowledge_status_label()
        self.refresh_agent_context()
        self._append_agent_message(
            "MSquared",
            "Ready. I can summarize selected intake, shape X posts or replies, draft email responses, and recommend escalation points. Public actions still need approval.",
        )

    def _build_composer_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        top = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Draft New Content", style="Panel.TLabel", font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        ttk.Label(top, text="Type", style="Panel.TLabel").pack(side=tk.LEFT, padx=(20, 6))
        ttk.Combobox(top, textvariable=self.composer_type, values=("x_post", "email_response"), width=16, state="readonly").pack(side=tk.LEFT)

        ttk.Label(parent, text="Context or topic").grid(row=1, column=0, sticky="w", pady=(10, 4))
        self.composer_text = tk.Text(parent, height=16, wrap=tk.WORD, font=("Segoe UI", 10), undo=True)
        self.composer_text.grid(row=2, column=0, sticky="nsew")

        buttons = ttk.Frame(parent)
        buttons.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(buttons, text="Generate Draft", style="Accent.TButton", command=self.generate_composer_draft).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Clear", command=lambda: self.composer_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=(6, 0))

    def _build_approval_tab(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="Refresh", command=self.refresh_queue).pack(side=tk.LEFT)
        ttk.Label(toolbar, text="Status").pack(side=tk.LEFT, padx=(16, 6))
        filter_picker = ttk.Combobox(
            toolbar,
            textvariable=self.queue_filter,
            values=("drafted", "needs_review", "approved", "rejected", "sent_or_posted", "archived", "all"),
            width=16,
            state="readonly",
        )
        filter_picker.pack(side=tk.LEFT)
        filter_picker.bind("<<ComboboxSelected>>", lambda _event: self.refresh_queue())
        ttk.Label(toolbar, text="Channel").pack(side=tk.LEFT, padx=(12, 6))
        channel_picker = ttk.Combobox(
            toolbar,
            textvariable=self.queue_channel_filter,
            values=("all", "x", "email"),
            width=10,
            state="readonly",
        )
        channel_picker.pack(side=tk.LEFT)
        channel_picker.bind("<<ComboboxSelected>>", lambda _event: self.refresh_queue())

        table_frame = ttk.Frame(parent, style="Panel.TFrame", padding=8)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("id", "channel", "type", "risk", "status", "created")
        self.queue_table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {"id": "ID", "channel": "Channel", "type": "Type", "risk": "Risk", "status": "Status", "created": "Created"}
        widths = {"id": 76, "channel": 74, "type": 110, "risk": 70, "status": 110, "created": 150}
        for column in columns:
            self.queue_table.heading(column, text=headings[column])
            self.queue_table.column(column, width=widths[column], minwidth=60, stretch=column == "created")
        self.queue_table.grid(row=0, column=0, sticky="nsew")
        queue_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.queue_table.yview)
        queue_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.queue_table.xview)
        self.queue_table.configure(yscrollcommand=queue_scroll_y.set, xscrollcommand=queue_scroll_x.set)
        queue_scroll_y.grid(row=0, column=1, sticky="ns")
        queue_scroll_x.grid(row=1, column=0, sticky="ew")
        self.queue_table.bind("<<TreeviewSelect>>", self.on_queue_select)

        detail = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        detail.grid(row=1, column=1, sticky="nsew")
        detail.rowconfigure(2, weight=1)
        detail.rowconfigure(5, weight=1)
        detail.columnconfigure(0, weight=1)
        ttk.Label(detail, text="Draft", style="Panel.TLabel", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.risk_label = ttk.Label(detail, text="No draft selected.", style="Panel.TLabel", foreground="#405166")
        self.risk_label.grid(row=1, column=0, sticky="ew", pady=(6, 4))
        self.draft_preview = tk.Text(detail, height=10, wrap=tk.WORD, font=("Segoe UI", 10), state=tk.DISABLED)
        self.draft_preview.grid(row=2, column=0, sticky="nsew")

        buttons = ttk.Frame(detail, style="Panel.TFrame")
        buttons.grid(row=3, column=0, sticky="ew", pady=(10, 8))
        self.approve_button = ttk.Button(buttons, text="Approve", command=self.approve_selected, state=tk.DISABLED)
        self.approve_button.pack(side=tk.LEFT)
        self.reject_button = ttk.Button(buttons, text="Reject", command=self.reject_selected, state=tk.DISABLED)
        self.reject_button.pack(side=tk.LEFT, padx=(6, 0))
        self.prepare_button = ttk.Button(buttons, text="Prepare Payload", command=self.prepare_selected_payload, state=tk.DISABLED)
        self.prepare_button.pack(side=tk.LEFT, padx=(6, 0))
        self.post_send_button = ttk.Button(buttons, text="Post/Send", command=self.execute_selected_action, state=tk.DISABLED)
        self.post_send_button.pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(detail, text="Payload / Result", style="Panel.TLabel", font=("Segoe UI", 11, "bold")).grid(row=4, column=0, sticky="w")
        self.payload_preview = tk.Text(detail, height=8, wrap=tk.WORD, font=("Consolas", 9), state=tk.DISABLED)
        self.payload_preview.grid(row=5, column=0, sticky="nsew", pady=(4, 0))

    def _build_settings_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        settings_tabs = ttk.Notebook(parent)
        settings_tabs.grid(row=0, column=0, sticky="nsew")

        admin_tab = ttk.Frame(settings_tabs)
        readiness_tab = ttk.Frame(settings_tabs, padding=10)
        settings_tabs.add(admin_tab, text="Admin")
        settings_tabs.add(readiness_tab, text="Readiness")

        admin_content = self._make_scrollable_frame(admin_tab)
        admin_content.configure(padding=10)
        self._build_admin_panel(admin_content)
        self._build_readiness_panel(readiness_tab)

    def _build_admin_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        values = read_env_values()
        values.update({f"__x_{key}": value or "" for key, value in x_connector_config().items()})
        values.update({f"__email_{key}": value or "" for key, value in email_connector_config().items()})
        values.setdefault("X_CONSUMER_KEY", values.get("X_API_KEY", ""))
        values.setdefault("X_CONSUMER_SECRET", values.get("X_API_SECRET", ""))
        values.setdefault("X_APP_PERMISSIONS", "Read and write")
        values.setdefault("X_APP_TYPE", "Web App, Automated App or Bot")
        values.setdefault("X_REQUEST_EMAIL_FROM_USERS", "false")
        values.setdefault("EMAIL_IMAP_SERVER", "imap.porkbun.com")
        values.setdefault("EMAIL_IMAP_PORT", "993")
        values.setdefault("EMAIL_IMAP_SECURITY", "SSL/TLS")
        values.setdefault("EMAIL_SMTP_SERVER", "smtp.porkbun.com")
        values.setdefault("EMAIL_SMTP_PORT", "587")
        values.setdefault("EMAIL_SMTP_SECURITY", "STARTTLS")
        values.setdefault("EMAIL_POP_SERVER", "pop.porkbun.com")
        values.setdefault("EMAIL_POP_PORT", "995")
        values.setdefault("EMAIL_POP_SECURITY", "SSL/TLS")
        values.setdefault("EMAIL_WEBMAIL_URL", "https://webmail.porkbun.com/")
        values.setdefault("EMAIL_MAILBOX", "inbox")
        values.setdefault("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        values.setdefault("PRODUCT_KNOWLEDGE_ROOTS", r"F:\code\diiac\itservices.diiac.io;F:\code\M-Squared-Architecture")
        values.setdefault("ALLOW_OPENAI_TECHNICAL_CONTEXT", "false")

        x_frame = ttk.LabelFrame(parent, text="X Developer Portal Settings", padding=10)
        x_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        x_frame.columnconfigure(1, weight=1)
        x_frame.columnconfigure(3, weight=1)
        ttk.Label(x_frame, text="Authentication settings", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        self._admin_combo(x_frame, 1, "App permissions", "X_APP_PERMISSIONS", values, ("Read", "Read and write", "Read and write and Direct message"))
        self._admin_combo(x_frame, 2, "Type of App", "X_APP_TYPE", values, ("Native App", "Web App, Automated App or Bot"))
        self._admin_entry(x_frame, 3, "Callback URI / Redirect URL", "X_CALLBACK_URI", values)
        self._admin_entry(x_frame, 4, "Website URL", "X_WEBSITE_URL", values)
        self._admin_entry(x_frame, 5, "Organization name", "X_ORGANIZATION_NAME", values)
        self._admin_entry(x_frame, 6, "Organization URL", "X_ORGANIZATION_URL", values)
        self._admin_entry(x_frame, 7, "Terms of Service", "X_TERMS_URL", values)
        self._admin_entry(x_frame, 8, "Privacy Policy", "X_PRIVACY_URL", values)
        self._admin_combo(x_frame, 9, "Request email from users", "X_REQUEST_EMAIL_FROM_USERS", values, ("false", "true"))

        ttk.Label(x_frame, text="Keys and tokens", font=("Segoe UI", 10, "bold")).grid(row=10, column=0, columnspan=4, sticky="w", pady=(12, 4))
        self._admin_entry(x_frame, 11, "Client ID", "X_CLIENT_ID", values, secret=True)
        self._admin_entry(x_frame, 12, "Client Secret", "X_CLIENT_SECRET", values, secret=True)
        self._admin_entry(x_frame, 13, "OAuth 2.0 Access Token", "X_OAUTH2_ACCESS_TOKEN", values, secret=True)
        self._admin_entry(x_frame, 14, "OAuth 2.0 Refresh Token", "X_OAUTH2_REFRESH_TOKEN", values, secret=True)
        self._admin_entry(x_frame, 15, "OAuth 2.0 Access Token Expires At", "X_OAUTH2_ACCESS_TOKEN_EXPIRES_AT", values)
        self._admin_entry(x_frame, 16, "OAuth 2.0 Scope", "X_OAUTH2_SCOPE", values)
        self._admin_entry(x_frame, 17, "App Bearer Token", "X_BEARER_TOKEN", values, secret=True)
        self._admin_entry(x_frame, 18, "OAuth 1.0a Consumer Key", "X_CONSUMER_KEY", values, secret=True)
        self._admin_entry(x_frame, 19, "OAuth 1.0a Consumer Key Secret", "X_CONSUMER_SECRET", values, secret=True)
        self._admin_entry(x_frame, 20, "OAuth 1.0a Access Token", "X_ACCESS_TOKEN", values, secret=True)
        self._admin_entry(x_frame, 21, "OAuth 1.0a Access Token Secret", "X_ACCESS_TOKEN_SECRET", values, secret=True)
        self._admin_entry(x_frame, 22, "MSquared numeric X user id", "X_MONITOR_USER_ID", values)
        self._admin_entry(x_frame, 23, "Monitor query", "X_MONITOR_QUERY", values)

        email_frame = ttk.LabelFrame(parent, text="Email Connector", padding=10)
        email_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))
        email_frame.columnconfigure(1, weight=1)
        self._admin_entry(email_frame, 0, "Email address", "EMAIL_ADDRESS", values)
        self._admin_entry(email_frame, 1, "Mailbox password", "EMAIL_PASSWORD", values, secret=True)
        self._admin_entry(email_frame, 2, "Mailbox", "EMAIL_MAILBOX", values)

        ttk.Label(email_frame, text="IMAP incoming", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 2))
        self._admin_entry(email_frame, 4, "IMAP host", "EMAIL_IMAP_SERVER", values)
        self._admin_entry(email_frame, 5, "IMAP port", "EMAIL_IMAP_PORT", values)
        self._admin_combo(email_frame, 6, "IMAP security", "EMAIL_IMAP_SECURITY", values, ("SSL/TLS", "STARTTLS", "None"))

        ttk.Label(email_frame, text="SMTP outgoing", font=("Segoe UI", 10, "bold")).grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 2))
        self._admin_entry(email_frame, 8, "SMTP host", "EMAIL_SMTP_SERVER", values)
        self._admin_entry(email_frame, 9, "SMTP port", "EMAIL_SMTP_PORT", values)
        self._admin_combo(email_frame, 10, "SMTP security", "EMAIL_SMTP_SECURITY", values, ("STARTTLS", "STARTTLS Alt.", "Implicit TLS", "SSL/TLS", "None"))

        ttk.Label(email_frame, text="POP and webmail reference", font=("Segoe UI", 10, "bold")).grid(row=11, column=0, columnspan=2, sticky="w", pady=(10, 2))
        self._admin_entry(email_frame, 12, "POP host", "EMAIL_POP_SERVER", values)
        self._admin_entry(email_frame, 13, "POP port", "EMAIL_POP_PORT", values)
        self._admin_combo(email_frame, 14, "POP security", "EMAIL_POP_SECURITY", values, ("SSL/TLS", "None"))
        self._admin_entry(email_frame, 15, "Webmail URL", "EMAIL_WEBMAIL_URL", values)
        mail_hint = (
            "Use the password set for msquared@diiac.io, not the Porkbun account password. "
            "Porkbun SMTP: 587 STARTTLS, 50587 STARTTLS Alt., or 465 Implicit TLS. "
            "Live sorting uses IMAP 993 SSL/TLS."
        )
        ttk.Label(email_frame, text=mail_hint, wraplength=430).grid(row=16, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ai_frame = ttk.LabelFrame(parent, text="AI Agent", padding=10)
        ai_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ai_frame.columnconfigure(1, weight=1)
        ai_frame.columnconfigure(3, weight=1)
        self._admin_entry(ai_frame, 0, "OpenAI API key", "OPENAI_API_KEY", values, secret=True)
        self._admin_entry(ai_frame, 1, "Model", "OPENAI_MODEL", values)
        self._admin_entry(ai_frame, 2, "Knowledge roots", "PRODUCT_KNOWLEDGE_ROOTS", values)
        self._admin_combo(ai_frame, 3, "Send technical snippets to OpenAI", "ALLOW_OPENAI_TECHNICAL_CONTEXT", values, ("false", "true"))
        ai_hint = (
            f"Default model is {DEFAULT_OPENAI_MODEL}. A 403 from OpenAI usually means this API key or project "
            "cannot use the configured model or endpoint; the Agent will fall back locally and log the reason."
        )
        ttk.Label(ai_frame, text=ai_hint, wraplength=920).grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))

        flags_frame = ttk.LabelFrame(parent, text="Feature Flags", padding=10)
        flags_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        flags = load_feature_flags()
        flag_columns = [ttk.Frame(flags_frame), ttk.Frame(flags_frame)]
        flag_columns[0].grid(row=0, column=0, sticky="nw", padx=(0, 28))
        flag_columns[1].grid(row=0, column=1, sticky="nw")
        for index, key in enumerate(DEFAULT_FEATURE_FLAGS):
            var = tk.BooleanVar(value=bool(flags.get(key)))
            self.admin_flag_vars[key] = var
            ttk.Checkbutton(flag_columns[index % 2], text=key, variable=var).pack(anchor=tk.W, pady=2)

        note = (
            "Credentials are saved in .env beside the portable exe. Keep that file private. "
            "Live posting/sending still requires an approved queue item."
        )
        ttk.Label(parent, text=note, wraplength=920).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))

        actions = ttk.Frame(parent)
        actions.grid(row=4, column=0, columnspan=2, sticky="ew")
        ttk.Checkbutton(actions, text="Show secrets", variable=self.show_secrets, command=self.toggle_secret_visibility).pack(side=tk.LEFT)
        ttk.Button(actions, text="Reload", command=self.reload_admin_settings).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Save Admin Settings", style="Accent.TButton", command=self.save_admin_settings).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(actions, text="Open Data Folder", command=self.open_data_folder).pack(side=tk.RIGHT, padx=(0, 8))

    def _build_readiness_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        notes = (
            "X read/write and email read/send are behind feature flags. Posting and sending require approved queue items. "
            "Keyword-search auto-replies and unsolicited DMs are blocked by default."
        )
        ttk.Label(parent, text=notes, wraplength=920).grid(row=0, column=0, sticky="w", pady=(0, 10))

        status_frame = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        status_frame.grid(row=1, column=0, sticky="nsew")
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(1, weight=1)
        header = ttk.Frame(status_frame, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Connector Readiness", style="Panel.TLabel", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="Validate", command=self.refresh_connector_status).pack(side=tk.RIGHT)
        ttk.Button(header, text="Test X Connection", command=self.test_x_connection).pack(side=tk.RIGHT, padx=(0, 8))
        self.connector_status_box = tk.Text(status_frame, height=12, wrap=tk.NONE, font=("Consolas", 9), state=tk.DISABLED)
        self.connector_status_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.refresh_connector_status()

    def _build_diagnostics_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="Refresh Diagnostics", command=self.refresh_diagnostics).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Copy Diagnostic Summary", command=self.copy_diagnostic_summary).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Open Data Folder", command=self.open_data_folder).pack(side=tk.RIGHT)

        diagnostics_tabs = ttk.Notebook(parent)
        diagnostics_tabs.grid(row=1, column=0, sticky="nsew")

        app_log_tab = ttk.Frame(diagnostics_tabs, padding=8)
        audit_tab = ttk.Frame(diagnostics_tabs, padding=8)
        runtime_tab = ttk.Frame(diagnostics_tabs, padding=8)
        diagnostics_tabs.add(app_log_tab, text="App Log")
        diagnostics_tabs.add(audit_tab, text="Audit Trail")
        diagnostics_tabs.add(runtime_tab, text="Readiness & Paths")

        for tab in (app_log_tab, audit_tab, runtime_tab):
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=1)

        self.app_log_box = tk.Text(app_log_tab, wrap=tk.NONE, font=("Consolas", 9), state=tk.DISABLED)
        self.app_log_box.grid(row=0, column=0, sticky="nsew")
        self.audit_log_box = tk.Text(audit_tab, wrap=tk.NONE, font=("Consolas", 9), state=tk.DISABLED)
        self.audit_log_box.grid(row=0, column=0, sticky="nsew")
        self.runtime_status_box = tk.Text(runtime_tab, wrap=tk.NONE, font=("Consolas", 9), state=tk.DISABLED)
        self.runtime_status_box.grid(row=0, column=0, sticky="nsew")

    def _admin_entry(self, parent, row, label, key, values, secret=False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=values.get(key, ""))
        self.admin_vars[key] = var
        entry = ttk.Entry(parent, textvariable=var, show="*" if secret and not self.show_secrets.get() else "")
        entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        if secret:
            self.secret_entries.append(entry)
        return entry

    def _admin_combo(self, parent, row, label, key, values, options):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=values.get(key, options[0]))
        self.admin_vars[key] = var
        combo = ttk.Combobox(parent, textvariable=var, values=options, state="readonly")
        combo.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        return combo

    def refresh_x(self):
        items = fetch_x_feed({})
        self.status_text.set(self._refresh_summary("x", len(items)))
        self.refresh_intake()
        self.refresh_diagnostics()

    def refresh_email(self):
        items = fetch_inbound_emails({})
        self.status_text.set(self._refresh_summary("email", len(items)))
        self.refresh_intake()
        self.refresh_diagnostics()

    def refresh_all_sources(self):
        x_items = fetch_x_feed({})
        email_items = fetch_inbound_emails({})
        x_summary = self._refresh_summary("x", len(x_items))
        email_summary = self._refresh_summary("email", len(email_items))
        self.status_text.set(f"{x_summary} {email_summary}")
        self.refresh_intake()
        self.refresh_diagnostics()

    def add_manual_intake(self):
        text = self.manual_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showinfo("Input needed", "Add the X post, mention, or email text first.")
            return
        channel = self.manual_channel.get()
        item = add_intake_item({
            "channel": channel,
            "source_type": self.manual_source_type.get(),
            "author": self.manual_from.get().strip() if channel == "x" else "",
            "from": self.manual_from.get().strip() if channel == "email" else "",
            "subject": self.manual_subject.get().strip(),
            "text": text,
        })
        log_event("manual_intake_added", "info", "Manual intake item added.", {"intake_id": item["id"], "channel": channel})
        self.manual_text.delete("1.0", tk.END)
        self.status_text.set(f"Added intake {item['id']}.")
        self.refresh_intake(select_item_id=item["id"])
        self.refresh_diagnostics()

    def _current_agent_context(self) -> dict:
        source = self.agent_context_source.get()
        if source == "none":
            return {}

        selected = None
        if source in {"auto", "selected_intake"}:
            item = self._selected_intake()
            if item:
                selected = {"kind": "intake", "item": item}
        if not selected and source in {"auto", "selected_draft"}:
            item = self._selected_queue_item()
            if item:
                selected = {"kind": "draft", "item": item}
        return {"selected": selected} if selected else {}

    def _update_agent_status_label(self):
        if not hasattr(self, "agent_status_label"):
            return
        status = agent_status()
        label = f"Mode: {status['mode']} | Model: {status['model']}"
        if status.get("openai_configured") and status.get("masked_api_key"):
            label += f" | Key: {status['masked_api_key']}"
        self.agent_status_label.configure(text=label)

    def refresh_agent_context(self):
        if not hasattr(self, "agent_context_box"):
            return
        self._update_agent_status_label()
        self._update_knowledge_status_label()
        self._set_text(self.agent_context_box, summarize_context(self._current_agent_context()))

    def _append_agent_message(self, role: str, text: str):
        if not hasattr(self, "agent_transcript"):
            return
        self.agent_transcript.configure(state=tk.NORMAL)
        self.agent_transcript.insert(tk.END, f"{role}:\n{text.strip()}\n\n")
        self.agent_transcript.see(tk.END)
        self.agent_transcript.configure(state=tk.DISABLED)
        self.agent_messages.append({"role": role, "content": text.strip()})
        self.agent_messages = self.agent_messages[-30:]

    def clear_agent_chat(self):
        self.agent_messages = []
        self._set_text(self.agent_transcript, "")
        self._append_agent_message("MSquared", "Ready.")
        self.status_text.set("Agent chat cleared.")

    def ask_agent_async(self):
        if self.agent_busy:
            return
        prompt = self.agent_prompt.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showinfo("Input needed", "Ask MSquared something first.")
            return

        context = self._current_agent_context()
        context["knowledge_mode"] = self.agent_knowledge_mode.get()
        history = list(self.agent_messages)
        self._append_agent_message("Operator", prompt)
        self.agent_prompt.delete("1.0", tk.END)
        self.agent_busy = True
        self.agent_ask_button.configure(state=tk.DISABLED)
        self.status_text.set("MSquared is thinking...")

        def worker():
            try:
                result = ask_agent(prompt, context, history)
                self.after(0, lambda: self._finish_agent_answer(result=result))
            except Exception as exc:
                self.after(0, lambda: self._finish_agent_answer(error=exc))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_agent_answer(self, result=None, error=None):
        self.agent_busy = False
        self.agent_ask_button.configure(state=tk.NORMAL)
        if error:
            log_event("agent_answer_failed", "error", "Interactive MSquared agent failed.", {"error": str(error)})
            self._append_agent_message("MSquared", f"I could not complete that request: {error}")
            self.status_text.set("Agent request failed. See Diagnostics.")
        else:
            self._append_agent_message("MSquared", result["answer"])
            if result.get("openai_error"):
                self._append_agent_message("System", f"OpenAI fallback used: {result['openai_error']}")
                self.status_text.set("Agent answered using local fallback after OpenAI failed. See Diagnostics.")
            else:
                self.status_text.set(f"Agent answered using {result['mode']} mode.")
        self.refresh_agent_context()
        self.refresh_diagnostics()

    def _update_knowledge_status_label(self):
        if not hasattr(self, "knowledge_status_label"):
            return
        status = knowledge_status()
        built_at = status.get("built_at") or "not built"
        counts = status.get("sensitivity_counts", {})
        text = (
            f"Index: {status.get('document_count', 0)} chunks | "
            f"public {counts.get('public_safe', 0)} / internal {counts.get('internal', 0)} | "
            f"built {built_at}"
        )
        self.knowledge_status_label.configure(text=text)

    def refresh_product_knowledge_async(self):
        if self.knowledge_busy:
            return
        self.knowledge_busy = True
        self.refresh_knowledge_button.configure(state=tk.DISABLED)
        self.status_text.set("Refreshing local product knowledge index...")

        def worker():
            try:
                result = build_product_knowledge_index()
                self.after(0, lambda: self._finish_product_knowledge_refresh(result=result))
            except Exception as exc:
                self.after(0, lambda: self._finish_product_knowledge_refresh(error=exc))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_product_knowledge_refresh(self, result=None, error=None):
        self.knowledge_busy = False
        self.refresh_knowledge_button.configure(state=tk.NORMAL)
        if error:
            log_event("knowledge_refresh_failed", "error", "Product knowledge refresh failed.", {"error": str(error)})
            messagebox.showerror("Knowledge refresh failed", str(error))
            self.status_text.set("Product knowledge refresh failed. See Diagnostics.")
        else:
            log_event("knowledge_refresh_complete", "info", "Product knowledge index refreshed.", result)
            self.status_text.set(f"Product knowledge refreshed: {result.get('document_count', 0)} chunks indexed.")
        self._update_knowledge_status_label()
        self.refresh_diagnostics()

    def copy_validation_packet(self):
        query = self.agent_prompt.get("1.0", tk.END).strip()
        if not query:
            query = self.agent_messages[-1]["content"] if self.agent_messages else ""
        packet = build_validation_packet(query, mode=self.agent_knowledge_mode.get())
        self.clipboard_clear()
        self.clipboard_append(packet)
        log_event("validation_packet_copied", "info", "Product validation packet copied for Coding Chat.", {"knowledge_mode": self.agent_knowledge_mode.get()})
        self.status_text.set("Validation packet copied for Coding Chat.")
        self.refresh_diagnostics()

    def create_agent_draft_from_prompt(self):
        content_type = self.agent_draft_type.get()
        prompt = self.agent_prompt.get("1.0", tk.END).strip()
        context = self._current_agent_context()
        selected = context.get("selected") or {}
        source = selected.get("item") if selected.get("kind") == "intake" else {}

        if content_type == "x_reply" and (not source or source.get("channel") != "x"):
            messagebox.showinfo("Select X intake", "Select an X intake item before drafting an X reply.")
            return
        if content_type == "email_response" and (not source or source.get("channel") != "email"):
            messagebox.showinfo("Select email intake", "Select an email intake item before drafting an email response.")
            return

        draft_input = prompt or (source or {}).get("text") or (source or {}).get("body") or ""
        if not draft_input and content_type == "x_post":
            draft_input = summarize_context(context)
        if not draft_input:
            messagebox.showinfo("Input needed", "Add a prompt or select an intake item first.")
            return

        draft_context = {"source": source} if source else context
        try:
            item = create_agent_draft(content_type, draft_input, draft_context)
        except Exception as exc:
            log_event("agent_draft_failed", "error", "Interactive MSquared agent draft creation failed.", {"error": str(exc), "type": content_type})
            messagebox.showerror("Agent draft failed", str(exc))
            self.status_text.set("Agent draft failed. See Diagnostics.")
            self.refresh_diagnostics()
            return
        item_context = item.get("context") or {}
        fallback_error = item_context.get("agent_openai_error")
        mode = item_context.get("agent_mode", "local")
        message = f"Created approval draft {item['id']} ({content_type}, {item['risk_level']} risk, {mode} mode)."
        if fallback_error:
            message += f"\nOpenAI fallback used: {fallback_error}"
            self.status_text.set("Agent created a local fallback draft for approval after OpenAI failed. See Diagnostics.")
        else:
            self.status_text.set(f"Agent created draft {item['id']} for approval.")
        self._append_agent_message("MSquared", message)
        self.tabs.select(self.approval_tab)
        self.refresh_queue(select_item_id=item["id"])
        self.refresh_agent_context()
        self.refresh_diagnostics()

    def refresh_intake(self, select_item_id=None):
        selected_channel = self.intake_channel_filter.get()
        items = list_intake(self.intake_filter.get())
        self.intake_items = items if selected_channel == "all" else [item for item in items if item.get("channel") == selected_channel]
        self.intake_table.delete(*self.intake_table.get_children())
        for item in self.intake_items:
            subject = item.get("subject") or item.get("text", "")
            self.intake_table.insert(
                "",
                tk.END,
                iid=item["id"],
                values=(
                    item.get("id", ""),
                    item.get("channel", ""),
                    item.get("source_type", ""),
                    item.get("from") or item.get("author", ""),
                    subject[:80],
                    item.get("status", ""),
                ),
            )
        if select_item_id and self.intake_table.exists(select_item_id):
            self.intake_table.selection_set(select_item_id)
            self.intake_table.focus(select_item_id)
            self.on_intake_select()
        elif self.intake_items:
            first_id = self.intake_items[0]["id"]
            self.intake_table.selection_set(first_id)
            self.intake_table.focus(first_id)
            self.on_intake_select()
        else:
            self.selected_intake_id = None
            self.intake_meta.configure(text="No intake items.")
            self._set_text(self.intake_preview, "")
        self.refresh_agent_context()

    def on_intake_select(self, _event=None):
        selected = self.intake_table.selection()
        if not selected:
            return
        self.selected_intake_id = selected[0]
        item = self._selected_intake()
        if not item:
            return
        meta = f"{item.get('channel')} / {item.get('source_type')} / {item.get('from') or item.get('author') or 'unknown'}"
        self.intake_meta.configure(text=meta)
        detail = item.get("text") or item.get("body") or ""
        if item.get("subject"):
            detail = f"Subject: {item['subject']}\n\n{detail}"
        self._set_text(self.intake_preview, detail)
        self.refresh_agent_context()

    def draft_from_intake(self, draft_type: str):
        item = self._selected_intake()
        if not item:
            messagebox.showinfo("Select intake", "Select an intake item first.")
            return
        if draft_type.startswith("x") and item.get("channel") != "x":
            messagebox.showinfo("Wrong channel", "Select an X intake item for X drafts.")
            return
        if draft_type.startswith("email") and item.get("channel") != "email":
            messagebox.showinfo("Wrong channel", "Select an email intake item for email drafts.")
            return
        draft = generate_draft(draft_type, item.get("text", ""), {"source": item})
        update_intake_status(item["id"], "drafted")
        log_event("draft_created_from_intake", "info", "Draft created from intake item.", {"intake_id": item["id"], "approval_item_id": draft["id"], "draft_type": draft_type, "risk_level": draft["risk_level"]})
        self.status_text.set(f"Created {draft_type} draft {draft['id']} from {item['id']} with {draft['risk_level']} risk.")
        self.refresh_intake(select_item_id=item["id"])
        self.tabs.select(self.approval_tab)
        self.refresh_queue(select_item_id=draft["id"])
        self.refresh_diagnostics()

    def archive_selected_intake(self):
        item = self._selected_intake()
        if item:
            update_intake_status(item["id"], "archived")
            log_event("intake_archived", "info", "Intake item archived.", {"intake_id": item["id"]})
            self.status_text.set(f"Archived intake {item['id']}.")
            self.refresh_intake()
            self.refresh_diagnostics()

    def generate_composer_draft(self):
        text = self.composer_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showinfo("Input needed", "Add context before generating a draft.")
            return
        item = generate_draft(self.composer_type.get(), text)
        log_event("composer_draft_created", "info", "Composer draft created.", {"approval_item_id": item["id"], "type": item["type"], "risk_level": item["risk_level"]})
        self.status_text.set(f"Draft {item['id']} added with {item['risk_level']} risk.")
        self.tabs.select(self.approval_tab)
        self.refresh_queue(select_item_id=item["id"])
        self.refresh_diagnostics()

    def refresh_queue(self, select_item_id=None):
        selected_filter = self.queue_filter.get()
        selected_channel = self.queue_channel_filter.get()
        all_items = list_queue()
        self.queue_items = all_items if selected_filter == "all" else [item for item in all_items if item.get("status") == selected_filter]
        if selected_channel != "all":
            self.queue_items = [item for item in self.queue_items if item.get("channel") == selected_channel]
        self.queue_table.delete(*self.queue_table.get_children())
        for item in self.queue_items:
            created = item.get("created_at") or item.get("timestamp") or ""
            self.queue_table.insert(
                "",
                tk.END,
                iid=item["id"],
                values=(
                    item.get("id", ""),
                    item.get("channel", ""),
                    item.get("type", ""),
                    item.get("risk_level", ""),
                    item.get("status", ""),
                    created[:19].replace("T", " "),
                ),
            )
        if select_item_id and self.queue_table.exists(select_item_id):
            self.queue_table.selection_set(select_item_id)
            self.queue_table.focus(select_item_id)
            self.on_queue_select()
        elif self.queue_items:
            first_id = self.queue_items[0]["id"]
            self.queue_table.selection_set(first_id)
            self.queue_table.focus(first_id)
            self.on_queue_select()
        else:
            self.selected_item_id = None
            self._set_text(self.draft_preview, "")
            self._set_text(self.payload_preview, "")
            self.risk_label.configure(text="No drafts match this filter.")
            self._update_action_buttons(None)
        self.refresh_agent_context()

    def on_queue_select(self, _event=None):
        selected = self.queue_table.selection()
        if not selected:
            return
        self.selected_item_id = selected[0]
        item = self._selected_queue_item()
        if not item:
            return
        self.prepared_payload_item_id = None
        self._set_text(self.draft_preview, item.get("draft", ""))
        self._set_text(self.payload_preview, "")
        risks = item.get("risks") or []
        claims = item.get("claims_checked") or []
        risk_detail = "; ".join(str(risk) for risk in risks[:3]) if risks else "none"
        self.risk_label.configure(
            text=f"Risk: {item.get('risk_level')} | Status: {item.get('status')} | Reasons: {risk_detail} | Claims checked: {len(claims)}"
        )
        self._update_action_buttons(item)
        self.refresh_agent_context()

    def approve_selected(self):
        if not self.selected_item_id:
            return
        try:
            item = approve_item(self.selected_item_id)
        except ValueError as exc:
            log_event("approval_failed", "warning", "Approval was blocked.", {"approval_item_id": self.selected_item_id, "error": str(exc)})
            messagebox.showerror("Approval blocked", str(exc))
            return
        if item:
            log_event("approval_granted", "info", "Draft approved in desktop console.", {"approval_item_id": self.selected_item_id})
            self.status_text.set(f"Approved {self.selected_item_id}. No public action has run.")
            self.refresh_queue(select_item_id=self.selected_item_id)
            self.refresh_diagnostics()

    def reject_selected(self):
        if not self.selected_item_id:
            return
        selected = self._selected_queue_item()
        reason = simpledialog.askstring("Reject draft", "Reason for rejection or rewrite request:")
        if reason is None:
            return
        if selected and selected.get("risk_level") == "block" and not reason.strip():
            messagebox.showinfo("Reason required", "Blocked drafts need a rejection or rewrite reason.")
            return
        try:
            item = reject_item(self.selected_item_id, reason=reason.strip())
        except ValueError as exc:
            log_event("rejection_failed", "warning", "Rejection was blocked.", {"approval_item_id": self.selected_item_id, "error": str(exc)})
            messagebox.showerror("Rejection blocked", str(exc))
            return
        if item:
            log_event("approval_rejected", "info", "Draft rejected in desktop console.", {"approval_item_id": self.selected_item_id, "risk_level": item.get("risk_level")})
            self.status_text.set(f"Rejected {self.selected_item_id}.")
            self.refresh_queue(select_item_id=self.selected_item_id)
            self.refresh_diagnostics()

    def prepare_selected_payload(self):
        item = self._selected_queue_item()
        if not item:
            return
        try:
            payload = prepare_x_payload(item["id"]) if item.get("channel") == "x" else prepare_email_payload(item["id"])
            self._set_text(self.payload_preview, json.dumps(payload, indent=2))
            self.prepared_payload_item_id = item["id"]
            self._update_action_buttons(item)
            self.status_text.set(f"Prepared payload for {item['id']}. Nothing was posted or sent.")
            self.refresh_diagnostics()
        except Exception as exc:
            log_event("payload_prepare_failed", "warning", "Payload preparation was blocked.", {"approval_item_id": item.get("id"), "error": str(exc)})
            messagebox.showerror("Payload blocked", str(exc))
            self.refresh_diagnostics()

    def execute_selected_action(self):
        item = self._selected_queue_item()
        if not item:
            return
        if self.prepared_payload_item_id != item["id"]:
            messagebox.showinfo("Prepare first", "Prepare and review the payload before using Post/Send.")
            return
        if not self._confirm_live_action_if_needed(item):
            return
        try:
            result = post_approved_tweet(item["id"], {}) if item.get("channel") == "x" else send_approved_email(item["id"], {})
            self._set_text(self.payload_preview, json.dumps(result, indent=2, default=str))
            self.status_text.set(f"Action checked for {item['id']}: {'sent' if result.get('sent') else result.get('reason')}.")
            self.refresh_queue(select_item_id=item["id"])
            self.refresh_diagnostics()
        except Exception as exc:
            log_event("execute_action_failed", "error", "Post/send action failed.", {"approval_item_id": item.get("id"), "channel": item.get("channel"), "error": str(exc)})
            messagebox.showerror("Action blocked", str(exc))
            self.refresh_diagnostics()

    def open_data_folder(self):
        data_dir = app_root() / "data"
        data_dir.mkdir(exist_ok=True)
        try:
            import os

            os.startfile(data_dir)
        except OSError as exc:
            messagebox.showerror("Could not open folder", str(exc))

    def refresh_connector_status(self):
        status = connector_status()
        self._set_text(self.connector_status_box, json.dumps(status, indent=2))
        self.status_text.set("Connector readiness refreshed. Secrets are masked or omitted.")
        self.refresh_diagnostics()

    def test_x_connection(self):
        try:
            result = test_x_connection({})
        except Exception as exc:
            log_event("x_connection_test_ui_failed", "error", "X connection test failed in desktop console.", {"error": str(exc)})
            messagebox.showerror("X connection test failed", str(exc))
            self.status_text.set("X connection test failed. See Diagnostics.")
            self.refresh_diagnostics()
            return

        status = connector_status()
        self._set_text(self.connector_status_box, json.dumps({"x_connection_test": result, "connector_readiness": status}, indent=2))
        if result.get("ok"):
            messagebox.showinfo("X connection test", result.get("message", "X connection test passed."))
            self.status_text.set("X connection test passed.")
        else:
            messagebox.showwarning("X connection test", result.get("message", "X connection test failed."))
            self.status_text.set("X connection test failed. See Diagnostics.")
        self.refresh_diagnostics()

    def refresh_diagnostics(self):
        if not hasattr(self, "app_log_box"):
            return
        app_events = read_log_events(limit=200)
        audit_records = read_audit_records()[-200:]
        runtime = {
            "paths": {
                "app_root": str(app_root()),
                "data_dir": str(app_root() / "data"),
                "app_log": str(APP_LOG_FILE),
                "audit_log": str(AUDIT_FILE),
                "approval_queue": str(app_root() / "data" / "approval_queue.json"),
            },
            "connector_readiness": connector_status(),
        }
        self._set_text(self.app_log_box, self._format_records(app_events, "event"))
        self._set_text(self.audit_log_box, self._format_records(audit_records, "action"))
        self._set_text(self.runtime_status_box, json.dumps(runtime, indent=2))

    def copy_diagnostic_summary(self):
        summary = {
            "recent_app_log": read_log_events(limit=50),
            "recent_audit": read_audit_records()[-50:],
            "readiness": connector_status(),
            "paths": {
                "app_root": str(app_root()),
                "data_dir": str(app_root() / "data"),
            },
        }
        text = json.dumps(summary, indent=2)
        self.clipboard_clear()
        self.clipboard_append(text)
        log_event("diagnostic_summary_copied", "info", "Diagnostic summary copied to clipboard.")
        self.status_text.set("Diagnostic summary copied. Secrets and content are redacted.")
        self.refresh_diagnostics()

    def toggle_secret_visibility(self):
        show = "" if self.show_secrets.get() else "*"
        for entry in self.secret_entries:
            entry.configure(show=show)

    def reload_admin_settings(self):
        values = read_env_values()
        values.setdefault("X_CONSUMER_KEY", values.get("X_API_KEY", ""))
        values.setdefault("X_CONSUMER_SECRET", values.get("X_API_SECRET", ""))
        values.setdefault("X_APP_PERMISSIONS", "Read and write")
        values.setdefault("X_APP_TYPE", "Web App, Automated App or Bot")
        values.setdefault("X_REQUEST_EMAIL_FROM_USERS", "false")
        values.setdefault("EMAIL_IMAP_SERVER", "imap.porkbun.com")
        values.setdefault("EMAIL_IMAP_PORT", "993")
        values.setdefault("EMAIL_IMAP_SECURITY", "SSL/TLS")
        values.setdefault("EMAIL_SMTP_SERVER", "smtp.porkbun.com")
        values.setdefault("EMAIL_SMTP_PORT", "587")
        values.setdefault("EMAIL_SMTP_SECURITY", "STARTTLS")
        values.setdefault("EMAIL_POP_SERVER", "pop.porkbun.com")
        values.setdefault("EMAIL_POP_PORT", "995")
        values.setdefault("EMAIL_POP_SECURITY", "SSL/TLS")
        values.setdefault("EMAIL_WEBMAIL_URL", "https://webmail.porkbun.com/")
        values.setdefault("EMAIL_MAILBOX", "inbox")
        values.setdefault("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        values.setdefault("PRODUCT_KNOWLEDGE_ROOTS", r"F:\code\diiac\itservices.diiac.io;F:\code\M-Squared-Architecture")
        values.setdefault("ALLOW_OPENAI_TECHNICAL_CONTEXT", "false")
        for key, var in self.admin_vars.items():
            var.set(values.get(key, ""))
        flags = load_feature_flags()
        for key, var in self.admin_flag_vars.items():
            var.set(bool(flags.get(key)))
        self.refresh_connector_status()
        self._update_agent_status_label()
        self.refresh_agent_context()
        log_event("admin_settings_reloaded", "info", "Admin settings reloaded from disk.")
        self.status_text.set("Admin settings reloaded from disk.")

    def save_admin_settings(self):
        flag_values = {key: var.get() for key, var in self.admin_flag_vars.items()}
        enabling_live = flag_values.get("ENABLE_X_WRITE") or flag_values.get("ENABLE_EMAIL_SEND")
        if enabling_live:
            confirmed = messagebox.askyesno(
                "Confirm live actions",
                "You are enabling live X posting and/or email sending. Approved queue items may be posted or sent. Continue?",
            )
            if not confirmed:
                return

        saved_flags = save_feature_flags(flag_values)
        env_values = {key: var.get().strip() for key, var in self.admin_vars.items()}
        if env_values.get("X_CONSUMER_KEY"):
            env_values["X_API_KEY"] = env_values["X_CONSUMER_KEY"]
        if env_values.get("X_CONSUMER_SECRET"):
            env_values["X_API_SECRET"] = env_values["X_CONSUMER_SECRET"]
        env_values.update({key: "true" if value else "false" for key, value in saved_flags.items()})
        env_path = save_env_values(env_values)
        self.refresh_connector_status()
        self._update_agent_status_label()
        self.refresh_agent_context()
        log_event(
            "admin_settings_saved",
            "info",
            "Admin settings saved.",
            {"env_path": str(env_path), "feature_flags": saved_flags, "configured_keys": sorted(env_values.keys())},
        )
        messagebox.showinfo("Settings saved", f"Saved admin settings to:\n{env_path}")
        self.status_text.set("Admin settings saved and connector readiness refreshed.")

    def _selected_intake(self):
        for item in self.intake_items:
            if item.get("id") == self.selected_intake_id:
                return item
        return None

    def _selected_queue_item(self):
        for item in self.queue_items:
            if item.get("id") == self.selected_item_id:
                return item
        return None

    def _set_text(self, widget, text: str):
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)

    def _update_action_buttons(self, item: dict | None):
        if not item:
            for button in (self.approve_button, self.reject_button, self.prepare_button, self.post_send_button):
                button.configure(state=tk.DISABLED)
            return
        can_decide = item.get("status") in {"drafted", "needs_review"}
        can_approve = can_decide and item.get("risk_level") != "block"
        can_prepare = item.get("status") == "approved" and item.get("risk_level") != "block"
        can_execute = can_prepare and self.prepared_payload_item_id == item.get("id")
        self.approve_button.configure(state=tk.NORMAL if can_approve else tk.DISABLED)
        self.reject_button.configure(state=tk.NORMAL if can_decide else tk.DISABLED)
        self.prepare_button.configure(state=tk.NORMAL if can_prepare else tk.DISABLED)
        self.post_send_button.configure(state=tk.NORMAL if can_execute else tk.DISABLED)

    def _confirm_live_action_if_needed(self, item: dict) -> bool:
        flags = load_feature_flags()
        status = connector_status()
        if item.get("channel") == "x":
            live_enabled = bool(flags.get("ENABLE_X_WRITE"))
            ready = bool(status["x"]["ready_to_write"])
            expected = "POST"
            target = "the configured MSquared X account"
        else:
            live_enabled = bool(flags.get("ENABLE_EMAIL_SEND"))
            ready = bool(status["email"]["ready_to_send"])
            expected = "SEND"
            target = "the approved email recipient"

        if not live_enabled:
            return True
        if not ready:
            messagebox.showerror("Connector not ready", "Live action is enabled, but connector readiness is incomplete. Check Diagnostics.")
            log_event("live_action_blocked", "warning", "Live action blocked because connector readiness is incomplete.", {"approval_item_id": item.get("id"), "channel": item.get("channel")})
            return False
        answer = simpledialog.askstring(
            "Confirm live action",
            f"This will {expected.lower()} now using {target}.\n\nType {expected} to continue:",
        )
        if answer != expected:
            log_event("live_action_cancelled", "info", "Live action confirmation was cancelled or did not match.", {"approval_item_id": item.get("id"), "channel": item.get("channel")})
            self.status_text.set("Live action cancelled. Nothing was posted or sent.")
            return False
        log_event("live_action_confirmed", "warning", "Operator confirmed a live post/send action.", {"approval_item_id": item.get("id"), "channel": item.get("channel")})
        return True

    def _refresh_summary(self, channel: str, item_count: int) -> str:
        prefix = f"{channel}_fetch_"
        for event in reversed(read_log_events(limit=40)):
            event_name = str(event.get("event", ""))
            if not event_name.startswith(prefix) or event_name.endswith("started"):
                continue
            level = str(event.get("level", "info")).upper()
            message = event.get("message", "")
            if event_name.endswith("failed"):
                return f"{channel.title()} refresh FAILED: {message} See Diagnostics. {item_count} item(s) imported or already present."
            if event_name.endswith("skipped"):
                return f"{channel.title()} refresh skipped: {message} {item_count} item(s) imported or already present."
            return f"{channel.title()} refresh {level.lower()}: {message} {item_count} item(s) imported or already present."
        return f"{channel.title()} refresh complete. {item_count} item(s) imported or already present."

    def _format_records(self, records: list, label_key: str) -> str:
        if not records:
            return "No records yet."
        lines = []
        for record in reversed(records):
            timestamp = record.get("timestamp", "")
            label = record.get(label_key, "")
            level = record.get("level") or record.get("final_action_status") or ""
            message = record.get("message") or record.get("reason") or ""
            lines.append(f"{timestamp} | {level} | {label} | {message}")
            lines.append(json.dumps(record, indent=2, default=str))
            lines.append("")
        return "\n".join(lines)


def main():
    app = MSquaredDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
