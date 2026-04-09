import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:file_picker/file_picker.dart';
import '../providers/auth_provider.dart';
import '../providers/chat_provider.dart';
import '../providers/cloud_provider.dart';
import '../providers/sessions_provider.dart';
import '../models/chat_session.dart';
import '../services/api_service.dart';
import '../theme.dart';
import '../widgets/answer_bubble.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _queryCtrl  = TextEditingController();
  final _scrollCtrl = ScrollController();
  final _focusNode  = FocusNode();

  int  _pendingCount = 0;
  bool _useWeb       = false;

  // Suggested starter questions
  final List<String> _suggestions = [
    'What is our leave policy?',
    'Show me Q1 2026 revenue',
    'Are we GDPR compliant?',
    'Who are our top customers?',
    'What R&D projects are active?',
    'How is our order fulfilment rate?',
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadPendingCount();
      _loadSessions();
    });
  }

  Future<void> _loadSessions() async {
    final auth = context.read<AuthProvider>();
    if (!auth.isLoggedIn) return;
    await context.read<SessionsProvider>().loadSessions();
  }

  void _showChangePasswordDialog(BuildContext ctx, AuthProvider auth) {
    final newPassCtrl = TextEditingController();
    final confirmCtrl = TextEditingController();
    bool saving = false;
    String? error;
    bool newVisible = false;
    bool confirmVisible = false;

    showDialog(
      context: ctx,
      builder: (dialogCtx) => StatefulBuilder(
        builder: (dialogCtx, setDialogState) => AlertDialog(
          backgroundColor: RapidColors.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Text('Change Password', style: TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w700)),
          content: SizedBox(
            width: 360,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'Enter a new password. You will use this to log in next time.',
                  style: TextStyle(color: RapidColors.textSecondary, fontSize: 13),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: newPassCtrl,
                  obscureText: !newVisible,
                  style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                  decoration: InputDecoration(
                    labelText: 'New password',
                    labelStyle: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
                    filled: true, fillColor: RapidColors.surfaceAlt,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
                    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
                    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent, width: 1.5)),
                    isDense: true, contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                    suffixIcon: IconButton(
                      icon: Icon(newVisible ? Icons.visibility_off : Icons.visibility, size: 16, color: RapidColors.textSecondary),
                      onPressed: () => setDialogState(() => newVisible = !newVisible),
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: confirmCtrl,
                  obscureText: !confirmVisible,
                  style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                  decoration: InputDecoration(
                    labelText: 'Confirm new password',
                    labelStyle: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
                    filled: true, fillColor: RapidColors.surfaceAlt,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
                    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
                    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent, width: 1.5)),
                    isDense: true, contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                    suffixIcon: IconButton(
                      icon: Icon(confirmVisible ? Icons.visibility_off : Icons.visibility, size: 16, color: RapidColors.textSecondary),
                      onPressed: () => setDialogState(() => confirmVisible = !confirmVisible),
                    ),
                  ),
                ),
                if (error != null) ...[
                  const SizedBox(height: 10),
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(color: RapidColors.error.withOpacity(0.1), borderRadius: BorderRadius.circular(8), border: Border.all(color: RapidColors.error.withOpacity(0.4))),
                    child: Row(children: [
                      const Icon(Icons.error_outline, color: RapidColors.error, size: 15),
                      const SizedBox(width: 6),
                      Expanded(child: Text(error!, style: const TextStyle(color: RapidColors.error, fontSize: 12))),
                    ]),
                  ),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogCtx),
              child: const Text('Cancel', style: TextStyle(color: RapidColors.textSecondary)),
            ),
            ElevatedButton(
              onPressed: saving ? null : () async {
                final newPass = newPassCtrl.text.trim();
                final confirm = confirmCtrl.text.trim();
                if (newPass.length < 8) {
                  setDialogState(() => error = 'Password must be at least 8 characters.');
                  return;
                }
                if (newPass != confirm) {
                  setDialogState(() => error = 'Passwords do not match.');
                  return;
                }
                setDialogState(() { saving = true; error = null; });
                try {
                  await ApiService.changePassword(
                    userId:          auth.userId!,
                    currentPassword: auth.password!,
                    newPassword:     newPass,
                  );
                  // Update the in-memory credential so current session stays valid
                  auth.updatePassword(newPass);
                  if (dialogCtx.mounted) Navigator.pop(dialogCtx);
                  if (ctx.mounted) {
                    ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                      content: Text('Password changed successfully.'),
                      backgroundColor: RapidColors.success,
                    ));
                  }
                } catch (e) {
                  setDialogState(() {
                    error = e.toString().replaceFirst('Exception: ', '');
                    saving = false;
                  });
                }
              },
              style: ElevatedButton.styleFrom(backgroundColor: RapidColors.accent, foregroundColor: Colors.white),
              child: saving
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Text('Update Password'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _loadPendingCount() async {
    final auth = context.read<AuthProvider>();
    if (!auth.isAdmin) return;
    try {
      final count = await ApiService.pendingRequestCount(userId: auth.userId!, password: auth.password!);
      if (mounted) setState(() => _pendingCount = count);
    } catch (_) {}
  }

  @override
  void dispose() {
    _queryCtrl.dispose();
    _scrollCtrl.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 350),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _send() async {
    final text = _queryCtrl.text.trim();
    if (text.isEmpty) return;
    final auth     = context.read<AuthProvider>();
    final chat     = context.read<ChatProvider>();
    final sessions = context.read<SessionsProvider>();
    _queryCtrl.clear();
    _focusNode.requestFocus();

    // Auto-create a session on the first message
    String? sessionId = chat.currentSessionId;
    if (sessionId == null) {
      try {
        final session = await sessions.createSession();
        sessionId = session.id;
        chat.setSession(sessionId);
      } catch (_) {
        // Non-fatal — proceed without session persistence
      }
    }

    await chat.sendQuery(
      queryText: text,
      useWeb:    _useWeb,
      sessionId: sessionId,
    );

    // Refresh sessions list so title update appears
    _loadSessions();
    _scrollToBottom();
  }

  Future<void> _pickFile() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['txt', 'pdf', 'md', 'csv', 'json', 'docx'],
      withData: true,
    );
    if (result != null && result.files.isNotEmpty) {
      final f = result.files.first;
      if (f.bytes != null) {
        context.read<ChatProvider>().attachFile(f.name, f.bytes!);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final chat = context.watch<ChatProvider>();
    final isWide = MediaQuery.of(context).size.width > 960;

    return Scaffold(
      backgroundColor: RapidColors.primary,
      appBar: _buildAppBar(auth, chat),
      body: Row(
        children: [
          // Narrow left sidebar — only on wide screens, minimal
          if (isWide) _buildSidebar(chat),

          // Main area
          Expanded(
            child: Column(
              children: [
                Expanded(
                  child: chat.messages.isEmpty
                    ? _buildEmptyState()
                    : _buildMessageList(chat),
                ),
                _buildInputArea(chat),
              ],
            ),
          ),
        ],
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(AuthProvider auth, ChatProvider chat) {
    return AppBar(
      backgroundColor: RapidColors.surface,
      elevation: 0,
      leading: Padding(
        padding: const EdgeInsets.all(12),
        child: Container(
          decoration: BoxDecoration(
            color: RapidColors.accent.withOpacity(0.15),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: RapidColors.accent.withOpacity(0.4)),
          ),
          child: const Center(
            child: Text('R', style: TextStyle(color: RapidColors.accent, fontWeight: FontWeight.w800, fontSize: 16)),
          ),
        ),
      ),
      title: const Text('RAPID', style: TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w700, letterSpacing: 1)),
      actions: [
        if (chat.messages.isNotEmpty)
          IconButton(
            icon: const Icon(Icons.edit_note_rounded, color: RapidColors.textSecondary, size: 20),
            tooltip: 'New chat',
            onPressed: () => chat.clearHistory(),
          ),
        if (auth.isManager)
          TextButton(
            onPressed: () => Navigator.pushNamed(context, '/audit'),
            child: const Text('Audit', style: TextStyle(color: RapidColors.textSecondary, fontSize: 13)),
          ),
        if (auth.isManager)
          TextButton(
            onPressed: () async {
              await Navigator.pushNamed(context, '/users');
              _loadPendingCount(); // refresh after returning
            },
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                const Text('Users', style: TextStyle(color: RapidColors.textSecondary, fontSize: 13)),
                if (auth.isAdmin && _pendingCount > 0)
                  Positioned(
                    top: -6, right: -10,
                    child: Container(
                      padding: const EdgeInsets.all(3),
                      decoration: const BoxDecoration(color: RapidColors.error, shape: BoxShape.circle),
                      constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
                      child: Text('$_pendingCount',
                        style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.w700),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        if (auth.isAdmin)
          TextButton(
            onPressed: () => Navigator.pushNamed(context, '/admin'),
            child: const Text('Admin', style: TextStyle(color: RapidColors.textSecondary, fontSize: 13)),
          ),
        IconButton(
          icon: const Icon(Icons.cloud_outlined, color: RapidColors.textSecondary, size: 20),
          tooltip: 'Cloud connections',
          onPressed: () => Navigator.pushNamed(context, '/cloud'),
        ),
        PopupMenuButton<String>(
          color: RapidColors.surface,
          icon: CircleAvatar(
            radius: 14,
            backgroundColor: RapidColors.accent.withOpacity(0.2),
            child: Text(
              auth.userId?.substring(0, 1).toUpperCase() ?? 'U',
              style: const TextStyle(color: RapidColors.accent, fontWeight: FontWeight.w700, fontSize: 13),
            ),
          ),
          onSelected: (v) async {
            if (v == 'logout') {
              await context.read<AuthProvider>().logout();
              Navigator.pushReplacementNamed(context, '/');
            } else if (v == 'change_password') {
              _showChangePasswordDialog(context, auth);
            } else if (v == 'my_access') {
              await Navigator.pushNamed(context, '/access');
            } else if (v == 'toggle_db') {
              final enabled = !auth.dbModeEnabled;
              try {
                await ApiService.toggleDbMode(
                  userId:   auth.userId!,
                  password: auth.password!,
                  enabled:  enabled,
                );
                auth.setDbMode(enabled);
              } catch (_) {}
            }
          },
          itemBuilder: (_) => [
            PopupMenuItem(
              enabled: false,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(auth.name ?? auth.userId ?? '',
                    style: const TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w600)),
                  Text(auth.role ?? '', style: const TextStyle(color: RapidColors.accent, fontSize: 11)),
                ],
              ),
            ),
            const PopupMenuDivider(),
            const PopupMenuItem(value: 'my_access', child: Row(
              children: [
                Icon(Icons.badge_outlined, size: 16, color: RapidColors.textSecondary),
                SizedBox(width: 8),
                Text('My access profile', style: TextStyle(color: RapidColors.textPrimary)),
              ],
            )),
            PopupMenuItem(value: 'toggle_db', child: Row(
              children: [
                Icon(Icons.storage_rounded, size: 16,
                  color: auth.dbModeEnabled ? RapidColors.accent : RapidColors.textSecondary),
                const SizedBox(width: 8),
                Text(auth.dbModeEnabled ? 'DB mode: ON' : 'DB mode: OFF',
                  style: TextStyle(
                    color: auth.dbModeEnabled ? RapidColors.accent : RapidColors.textPrimary,
                    fontWeight: auth.dbModeEnabled ? FontWeight.w600 : FontWeight.normal,
                  )),
              ],
            )),
            const PopupMenuItem(value: 'change_password', child: Row(
              children: [
                Icon(Icons.lock_reset_outlined, size: 16, color: RapidColors.textSecondary),
                SizedBox(width: 8),
                Text('Change password', style: TextStyle(color: RapidColors.textPrimary)),
              ],
            )),
            const PopupMenuDivider(),
            const PopupMenuItem(value: 'logout', child: Row(
              children: [
                Icon(Icons.logout, size: 16, color: RapidColors.textSecondary),
                SizedBox(width: 8),
                Text('Sign out', style: TextStyle(color: RapidColors.textPrimary)),
              ],
            )),
          ],
        ),
        const SizedBox(width: 8),
      ],
    );
  }

  Widget _buildSidebar(ChatProvider chat) {
    final auth     = context.watch<AuthProvider>();
    final sessions = context.watch<SessionsProvider>();

    return Container(
      width: 220,
      decoration: const BoxDecoration(
        color: RapidColors.surface,
        border: Border(right: BorderSide(color: RapidColors.divider)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // New chat button
          Padding(
            padding: const EdgeInsets.all(10),
            child: InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: () async {
                chat.clearHistory();
                // Don't pre-create session — it's created on first send
                sessions.setActive(null);
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                decoration: BoxDecoration(
                  border: Border.all(color: RapidColors.divider),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.add, color: RapidColors.textSecondary, size: 16),
                    SizedBox(width: 8),
                    Text('New chat', style: TextStyle(color: RapidColors.textSecondary, fontSize: 13)),
                  ],
                ),
              ),
            ),
          ),
          const Divider(height: 1, color: RapidColors.divider),

          // Session history list
          Expanded(
            child: sessions.loading
              ? const Center(child: SizedBox(width: 18, height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2, color: RapidColors.accent)))
              : sessions.sessions.isEmpty
                ? const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text('No previous chats', style: TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                  )
                : ListView(
                    padding: const EdgeInsets.only(bottom: 12),
                    children: [
                      ..._sessionGroup('Today',        sessions.todaySessions,      sessions, chat, auth),
                      ..._sessionGroup('Yesterday',    sessions.yesterdaySessions,  sessions, chat, auth),
                      ..._sessionGroup('Last 7 days',  sessions.last7DaysSessions,  sessions, chat, auth),
                      ..._sessionGroup('Older',        sessions.olderSessions,      sessions, chat, auth),
                    ],
                  ),
          ),

          // ── Cloud connectors status ────────────────────────────────────────
          _buildCloudConnectorSection(),
        ],
      ),
    );
  }

  Widget _buildCloudConnectorSection() {
    final cloud = context.watch<CloudProvider>();
    final oneDriveConnected = cloud.onedriveStatus?.connected ?? false;
    final gmailConnected    = cloud.gmailStatus?.connected    ?? false;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Divider(height: 1, color: RapidColors.divider),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
          child: Row(
            children: [
              const Text('CONNECTORS',
                style: TextStyle(
                  color: RapidColors.textSecondary,
                  fontSize: 9,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                ),
              ),
              const Spacer(),
              InkWell(
                borderRadius: BorderRadius.circular(4),
                onTap: () => Navigator.pushNamed(context, '/cloud'),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                  child: Text('Manage',
                    style: TextStyle(color: RapidColors.accent, fontSize: 9, fontWeight: FontWeight.w600)),
                ),
              ),
            ],
          ),
        ),
        _ConnectorTile(
          icon:      Icons.cloud_queue,
          label:     'OneDrive',
          email:     cloud.onedriveStatus?.email,
          connected: oneDriveConnected,
          color:     const Color(0xFF0078D4),
          onTap:     () => Navigator.pushNamed(context, '/cloud'),
        ),
        _ConnectorTile(
          icon:      Icons.mail_outline,
          label:     'Gmail',
          email:     cloud.gmailStatus?.email,
          connected: gmailConnected,
          color:     const Color(0xFFEA4335),
          onTap:     () => Navigator.pushNamed(context, '/cloud'),
        ),
        const SizedBox(height: 10),
      ],
    );
  }

  List<Widget> _sessionGroup(
    String label,
    List<ChatSession> items,
    SessionsProvider sessions,
    ChatProvider chat,
    AuthProvider auth,
  ) {
    if (items.isEmpty) return [];
    return [
      Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 4),
        child: Text(label,
          style: const TextStyle(color: RapidColors.textSecondary, fontSize: 10,
            fontWeight: FontWeight.w600, letterSpacing: 0.6)),
      ),
      ...items.map((s) => _SessionTile(
        session:   s,
        isActive:  sessions.activeSessionId == s.id,
        onTap: () async {
          try {
            await sessions.loadMessages(s.id, chat);
          } catch (e) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                content: Text('Could not load session: $e'),
                backgroundColor: RapidColors.error,
              ));
            }
          }
        },
        onDelete: () async {
          try {
            await sessions.deleteSession(s.id);
            if (chat.currentSessionId == s.id) chat.clearHistory();
          } catch (e) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                content: Text('Delete failed: $e'),
                backgroundColor: RapidColors.error,
              ));
            }
          }
        },
      )),
    ];
  }

  Widget _buildMessageList(ChatProvider chat) {
    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 8),
      itemCount: chat.messages.length + (chat.loading ? 1 : 0),
      itemBuilder: (ctx, i) {
        if (i == chat.messages.length) return const TypingIndicator();
        final msg = chat.messages[i];
        final ts = '${msg.timestamp.hour.toString().padLeft(2,'0')}:${msg.timestamp.minute.toString().padLeft(2,'0')}';
        if (msg.isUser) return UserBubble(text: msg.text, timestamp: ts, attachedFile: msg.attachedFileName);
        return AnswerBubble(message: msg);
      },
    );
  }

  Widget _buildInputArea(ChatProvider chat) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 20),
      decoration: const BoxDecoration(
        color: RapidColors.surface,
        border: Border(top: BorderSide(color: RapidColors.divider)),
      ),
      child: Column(
        children: [
          // Attachment preview
          if (chat.hasAttachment) ...[
            Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: RapidColors.accent.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: RapidColors.accent.withOpacity(0.4)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.insert_drive_file_outlined, color: RapidColors.accent, size: 16),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(chat.pendingFileName ?? '', style: const TextStyle(color: RapidColors.accent, fontSize: 13)),
                  ),
                  GestureDetector(
                    onTap: () => chat.clearAttachment(),
                    child: const Icon(Icons.close, color: RapidColors.textSecondary, size: 16),
                  ),
                ],
              ),
            ),
          ],

          // Input row
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              // Attach file
              IconButton(
                icon: const Icon(Icons.attach_file_rounded, color: RapidColors.textSecondary, size: 20),
                tooltip: 'Attach file',
                onPressed: chat.loading ? null : _pickFile,
              ),

              // Web search toggle
              Tooltip(
                message: _useWeb ? 'Web search ON — click to disable' : 'Web search OFF — click to enable',
                child: GestureDetector(
                  onTap: chat.loading ? null : () => setState(() => _useWeb = !_useWeb),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    margin: const EdgeInsets.only(right: 4),
                    decoration: BoxDecoration(
                      color: _useWeb ? RapidColors.accent.withOpacity(0.15) : Colors.transparent,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: _useWeb ? RapidColors.accent : RapidColors.divider,
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.public_rounded,
                          size: 14,
                          color: _useWeb ? RapidColors.accent : RapidColors.textSecondary,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          'Web',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: _useWeb ? RapidColors.accent : RapidColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),

              // Text input
              Expanded(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 160),
                  child: TextField(
                    controller: _queryCtrl,
                    focusNode: _focusNode,
                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 14),
                    maxLines: null,
                    keyboardType: TextInputType.multiline,
                    textInputAction: TextInputAction.newline,
                    decoration: const InputDecoration(
                      hintText: 'Message RAPID…',
                      hintStyle: TextStyle(color: RapidColors.textSecondary),
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      contentPadding: EdgeInsets.symmetric(horizontal: 4, vertical: 10),
                      isDense: true,
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
              ),

              // Send button
              GestureDetector(
                onTap: chat.loading ? null : _send,
                child: Container(
                  width: 36, height: 36,
                  decoration: BoxDecoration(
                    color: chat.loading ? RapidColors.divider : RapidColors.accent,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: chat.loading
                    ? const Center(child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)))
                    : const Icon(Icons.arrow_upward_rounded, color: Colors.white, size: 18),
                ),
              ),
            ],
          ),

          // Hint
          const SizedBox(height: 6),
          const Text(
            'RAPID searches your documents and databases — answers are governed and audited.',
            style: TextStyle(color: RapidColors.textSecondary, fontSize: 11),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 64, height: 64,
              decoration: BoxDecoration(
                color: RapidColors.accent.withOpacity(0.1),
                shape: BoxShape.circle,
                border: Border.all(color: RapidColors.accent.withOpacity(0.3)),
              ),
              child: const Center(child: Text('R', style: TextStyle(color: RapidColors.accent, fontSize: 30, fontWeight: FontWeight.w800))),
            ),
            const SizedBox(height: 18),
            const Text('How can I help you today?', style: TextStyle(color: RapidColors.textPrimary, fontSize: 22, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            const Text(
              "Ask anything about your company \u2014 I'll search your documents and databases.",
              style: TextStyle(color: RapidColors.textSecondary, fontSize: 14),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 32),
            Wrap(
              spacing: 10, runSpacing: 10,
              alignment: WrapAlignment.center,
              children: _suggestions.map((s) => _SuggestionChip(
                text: s,
                onTap: () {
                  _queryCtrl.text = s;
                  _send();
                },
              )).toList(),
            ),
          ],
        ),
      ),
    );
  }
}

class _SuggestionChip extends StatelessWidget {
  final String text;
  final VoidCallback onTap;
  const _SuggestionChip({required this.text, required this.onTap});

  @override
  Widget build(BuildContext context) => InkWell(
    borderRadius: BorderRadius.circular(20),
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: RapidColors.divider),
      ),
      child: Text(text, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 13)),
    ),
  );
}

class _SessionTile extends StatelessWidget {
  final ChatSession session;
  final bool isActive;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  const _SessionTile({
    required this.session,
    required this.isActive,
    required this.onTap,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      child: InkWell(
        borderRadius: BorderRadius.circular(6),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          decoration: BoxDecoration(
            color: isActive ? RapidColors.accent.withOpacity(0.12) : Colors.transparent,
            borderRadius: BorderRadius.circular(6),
            border: isActive
              ? Border.all(color: RapidColors.accent.withOpacity(0.3))
              : null,
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  session.title,
                  style: TextStyle(
                    color: isActive ? RapidColors.accent : RapidColors.textSecondary,
                    fontSize: 12,
                    fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              InkWell(
                onTap: onDelete,
                borderRadius: BorderRadius.circular(4),
                child: const Padding(
                  padding: EdgeInsets.all(2),
                  child: Icon(Icons.close, size: 12, color: RapidColors.textSecondary),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Connector status tile (used in sidebar)
// ─────────────────────────────────────────────────────────────────────────────

class _ConnectorTile extends StatelessWidget {
  final IconData  icon;
  final String    label;
  final String?   email;
  final bool      connected;
  final Color     color;
  final VoidCallback onTap;

  const _ConnectorTile({
    required this.icon,
    required this.label,
    required this.connected,
    required this.color,
    required this.onTap,
    this.email,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        child: Row(
          children: [
            Container(
              width: 26, height: 26,
              decoration: BoxDecoration(
                color: color.withValues(alpha: connected ? 0.15 : 0.07),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Icon(icon, size: 14,
                color: connected ? color : RapidColors.textSecondary),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label,
                    style: TextStyle(
                      color: connected ? RapidColors.textPrimary : RapidColors.textSecondary,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  if (connected && email != null)
                    Text(email!,
                      style: const TextStyle(color: RapidColors.textSecondary, fontSize: 10),
                      overflow: TextOverflow.ellipsis,
                    )
                  else
                    const Text('Not connected',
                      style: TextStyle(color: RapidColors.textSecondary, fontSize: 10)),
                ],
              ),
            ),
            Container(
              width: 7, height: 7,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: connected ? RapidColors.success : RapidColors.divider,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
