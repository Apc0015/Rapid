import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../providers/auth_provider.dart';
import '../providers/cloud_provider.dart';
import '../models/cloud_models.dart';
import '../theme.dart';

const List<String> _deptOptions = [
  'hr', 'finance', 'legal', 'sales', 'marketing',
  'ops', 'it', 'procurement', 'rd', 'customer_success',
];

class CloudScreen extends StatefulWidget {
  const CloudScreen({super.key});

  @override
  State<CloudScreen> createState() => _CloudScreenState();
}

class _CloudScreenState extends State<CloudScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _checkStatus());
  }

  Future<void> _checkStatus() async {
    final cloud = context.read<CloudProvider>();
    await cloud.checkStatus();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: RapidColors.primary,
      appBar: AppBar(
        backgroundColor: RapidColors.surface,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: RapidColors.textSecondary, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('Cloud Connections',
          style: TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w700)),
      ),
      body: LayoutBuilder(builder: (ctx, constraints) {
        final isWide = constraints.maxWidth > 800;
        if (isWide) {
          return Row(
            children: [
              Expanded(child: _OneDrivePanel()),
              const VerticalDivider(width: 1, color: RapidColors.divider),
              Expanded(child: _GmailPanel()),
            ],
          );
        }
        return SingleChildScrollView(
          child: Column(
            children: [
              _OneDrivePanel(),
              const Divider(color: RapidColors.divider),
              _GmailPanel(),
            ],
          ),
        );
      }),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// OneDrive Panel
// ─────────────────────────────────────────────────────────────────────────────

class _OneDrivePanel extends StatefulWidget {
  @override
  State<_OneDrivePanel> createState() => _OneDrivePanelState();
}

class _OneDrivePanelState extends State<_OneDrivePanel> {
  bool _connecting = false;
  String _importDept = _deptOptions.first;
  String? _importingId;

  Future<void> _connect() async {
    final cloud = context.read<CloudProvider>();
    setState(() => _connecting = true);
    try {
      final url = await cloud.onedriveAuthUrl();
      if (!await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication)) {
        throw Exception('Could not open browser');
      }
      // Poll for connection
      final connected = await cloud.waitForOnedriveConnection();
      if (connected && mounted) {
        await cloud.loadOnedriveFiles();
      } else if (!connected && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('OneDrive connection timed out. Please try again.'),
          backgroundColor: RapidColors.warning,
        ));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(e.toString().replaceFirst('Exception: ', '')),
          backgroundColor: RapidColors.error,
        ));
      }
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  Future<void> _disconnect() async {
    final cloud = context.read<CloudProvider>();
    try {
      await cloud.disconnectOnedrive();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Disconnect failed: $e'),
          backgroundColor: RapidColors.error,
        ));
      }
    }
  }

  Future<void> _loadFiles() async {
    final cloud = context.read<CloudProvider>();
    await cloud.loadOnedriveFiles();
  }

  Future<void> _import(String itemId) async {
    final cloud = context.read<CloudProvider>();
    setState(() => _importingId = itemId);
    await cloud.importOnedriveFile(itemId, _importDept);
    setState(() => _importingId = null);
    if (mounted && cloud.importResult != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(cloud.importResult!), backgroundColor: RapidColors.success));
    } else if (mounted && cloud.importError != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(cloud.importError!), backgroundColor: RapidColors.error));
    }
  }

  @override
  Widget build(BuildContext context) {
    final cloud  = context.watch<CloudProvider>();
    final status = cloud.onedriveStatus;
    final connected = status?.connected ?? false;

    return Container(
      color: RapidColors.primary,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(20),
            color: RapidColors.surface,
            child: Row(
              children: [
                Container(
                  width: 40, height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFF0078D4).withOpacity(0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.cloud, color: Color(0xFF0078D4), size: 22),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('OneDrive',
                        style: TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 16)),
                      Text(
                        connected ? (status?.email ?? 'Connected') : 'Not connected',
                        style: TextStyle(
                          color: connected ? RapidColors.success : RapidColors.textSecondary,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                if (connected)
                  TextButton(
                    onPressed: _disconnect,
                    child: const Text('Disconnect', style: TextStyle(color: RapidColors.error, fontSize: 12)),
                  ),
              ],
            ),
          ),

          if (!connected) ...[
            // Connect section
            Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Connect your OneDrive to import files into RAPID.',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 14)),
                  const SizedBox(height: 8),
                  const Text('Supported: .txt, .pdf, .md, .csv, .json, .docx',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                  const SizedBox(height: 20),
                  ElevatedButton.icon(
                    onPressed: _connecting ? null : _connect,
                    icon: _connecting
                      ? const SizedBox(width: 16, height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.link, size: 18),
                    label: Text(_connecting ? 'Waiting for authorization…' : 'Connect OneDrive'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF0078D4),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    ),
                  ),
                ],
              ),
            ),
          ] else ...[
            // Dept selector + refresh
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
              child: Row(
                children: [
                  const Text('Import to dept:', style: TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                  const SizedBox(width: 8),
                  DropdownButton<String>(
                    value: _importDept,
                    dropdownColor: RapidColors.surface,
                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 12),
                    onChanged: (v) => setState(() => _importDept = v!),
                    items: _deptOptions.map((d) => DropdownMenuItem(value: d, child: Text(d))).toList(),
                  ),
                  const Spacer(),
                  TextButton.icon(
                    onPressed: _loadFiles,
                    icon: const Icon(Icons.refresh, size: 14, color: RapidColors.textSecondary),
                    label: const Text('Refresh', style: TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                  ),
                ],
              ),
            ),
            // File list
            Expanded(
              child: cloud.loadingOnedrive
                ? const Center(child: CircularProgressIndicator(color: RapidColors.accent))
                : cloud.onedriveFiles.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.folder_open, color: RapidColors.textSecondary, size: 40),
                          const SizedBox(height: 8),
                          const Text('No files loaded', style: TextStyle(color: RapidColors.textSecondary)),
                          const SizedBox(height: 12),
                          TextButton(onPressed: _loadFiles, child: const Text('Load files')),
                        ],
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      itemCount: cloud.onedriveFiles.length,
                      itemBuilder: (ctx, i) {
                        final f = cloud.onedriveFiles[i];
                        return _CloudFileTile(
                          file:      f,
                          importing: _importingId == f.id,
                          onImport:  f.isFolder ? null : () => _import(f.id),
                        );
                      },
                    ),
            ),
          ],
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Gmail Panel
// ─────────────────────────────────────────────────────────────────────────────

class _GmailPanel extends StatefulWidget {
  @override
  State<_GmailPanel> createState() => _GmailPanelState();
}

class _GmailPanelState extends State<_GmailPanel> {
  bool _connecting    = false;
  String _importDept  = _deptOptions.first;
  String? _importingId;

  Future<void> _connect() async {
    final cloud = context.read<CloudProvider>();
    setState(() => _connecting = true);
    try {
      final url = await cloud.gmailAuthUrl();
      if (!await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication)) {
        throw Exception('Could not open browser');
      }
      final connected = await cloud.waitForGmailConnection();
      if (connected && mounted) {
        await cloud.loadGmailLabels();
      } else if (!connected && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Gmail connection timed out. Please try again.'),
          backgroundColor: RapidColors.warning,
        ));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(e.toString().replaceFirst('Exception: ', '')),
          backgroundColor: RapidColors.error,
        ));
      }
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  Future<void> _disconnect() async {
    final cloud = context.read<CloudProvider>();
    try {
      await cloud.disconnectGmail();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Disconnect failed: $e'),
          backgroundColor: RapidColors.error,
        ));
      }
    }
  }

  Future<void> _importMessage(String messageId) async {
    final cloud = context.read<CloudProvider>();
    setState(() => _importingId = messageId);
    await cloud.importGmailMessage(messageId, _importDept);
    setState(() => _importingId = null);
    if (mounted && cloud.importResult != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(cloud.importResult!), backgroundColor: RapidColors.success));
    } else if (mounted && cloud.importError != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(cloud.importError!), backgroundColor: RapidColors.error));
    }
  }

  @override
  Widget build(BuildContext context) {
    final cloud     = context.watch<CloudProvider>();
    final status    = cloud.gmailStatus;
    final connected = status?.connected ?? false;

    return Container(
      color: RapidColors.primary,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(20),
            color: RapidColors.surface,
            child: Row(
              children: [
                Container(
                  width: 40, height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFFEA4335).withOpacity(0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.mail_outline, color: Color(0xFFEA4335), size: 22),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Gmail',
                        style: TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 16)),
                      Text(
                        connected ? (status?.email ?? 'Connected') : 'Not connected',
                        style: TextStyle(
                          color: connected ? RapidColors.success : RapidColors.textSecondary,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                if (connected)
                  TextButton(
                    onPressed: _disconnect,
                    child: const Text('Disconnect', style: TextStyle(color: RapidColors.error, fontSize: 12)),
                  ),
              ],
            ),
          ),

          if (!connected) ...[
            Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Connect your Gmail to import emails and attachments into RAPID.',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 14)),
                  const SizedBox(height: 8),
                  const Text('Imports email body text and attachments (.pdf, .docx, etc.).',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                  const SizedBox(height: 20),
                  ElevatedButton.icon(
                    onPressed: _connecting ? null : _connect,
                    icon: _connecting
                      ? const SizedBox(width: 16, height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.link, size: 18),
                    label: Text(_connecting ? 'Waiting for authorization…' : 'Connect Gmail'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFFEA4335),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    ),
                  ),
                ],
              ),
            ),
          ] else ...[
            // Label selector + dept dropdown
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
              child: Row(
                children: [
                  const Text('Import to dept:', style: TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                  const SizedBox(width: 8),
                  DropdownButton<String>(
                    value: _importDept,
                    dropdownColor: RapidColors.surface,
                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 12),
                    onChanged: (v) => setState(() => _importDept = v!),
                    items: _deptOptions.map((d) => DropdownMenuItem(value: d, child: Text(d))).toList(),
                  ),
                ],
              ),
            ),

            // Labels list + messages side by side (or stacked on narrow)
            Expanded(
              child: cloud.loadingGmail
                ? const Center(child: CircularProgressIndicator(color: RapidColors.accent))
                : Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Labels sidebar
                      SizedBox(
                        width: 160,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Padding(
                              padding: EdgeInsets.fromLTRB(12, 8, 12, 4),
                              child: Text('Labels', style: TextStyle(color: RapidColors.textSecondary, fontSize: 10, fontWeight: FontWeight.w600, letterSpacing: 0.5)),
                            ),
                            Expanded(
                              child: cloud.gmailLabels.isEmpty
                                ? TextButton(
                                    onPressed: () async {
                                      await cloud.loadGmailLabels();
                                    },
                                    child: const Text('Load labels', style: TextStyle(fontSize: 12)),
                                  )
                                : ListView(
                                    padding: const EdgeInsets.symmetric(vertical: 4),
                                    children: cloud.gmailLabels.map((l) => InkWell(
                                      onTap: () async {
                                        await cloud.loadGmailMessages(l.id);
                                      },
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                        color: cloud.selectedGmailLabelId == l.id
                                          ? RapidColors.accent.withOpacity(0.1) : null,
                                        child: Text(l.name,
                                          style: TextStyle(
                                            color: cloud.selectedGmailLabelId == l.id
                                              ? RapidColors.accent : RapidColors.textSecondary,
                                            fontSize: 12,
                                          ),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                    )).toList(),
                                  ),
                            ),
                          ],
                        ),
                      ),
                      const VerticalDivider(width: 1, color: RapidColors.divider),
                      // Messages list
                      Expanded(
                        child: cloud.gmailMessages.isEmpty
                          ? const Center(
                              child: Text('Select a label to view messages.',
                                style: TextStyle(color: RapidColors.textSecondary, fontSize: 13)),
                            )
                          : ListView.builder(
                              itemCount: cloud.gmailMessages.length,
                              itemBuilder: (ctx, i) {
                                final m = cloud.gmailMessages[i];
                                final isImporting = _importingId == m.id;
                                return ListTile(
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                                  title: Text(m.subject,
                                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13, fontWeight: FontWeight.w500),
                                    maxLines: 1, overflow: TextOverflow.ellipsis),
                                  subtitle: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(m.from, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11),
                                        maxLines: 1, overflow: TextOverflow.ellipsis),
                                      Text(m.snippet, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11),
                                        maxLines: 1, overflow: TextOverflow.ellipsis),
                                    ],
                                  ),
                                  trailing: isImporting
                                    ? const SizedBox(width: 18, height: 18,
                                        child: CircularProgressIndicator(strokeWidth: 2, color: RapidColors.accent))
                                    : TextButton(
                                        onPressed: () => _importMessage(m.id),
                                        child: const Text('Import', style: TextStyle(fontSize: 12, color: RapidColors.accent)),
                                      ),
                                );
                              },
                            ),
                      ),
                    ],
                  ),
            ),
          ],
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared widgets
// ─────────────────────────────────────────────────────────────────────────────

class _CloudFileTile extends StatelessWidget {
  final CloudFile file;
  final bool importing;
  final VoidCallback? onImport;

  const _CloudFileTile({required this.file, required this.importing, this.onImport});

  @override
  Widget build(BuildContext context) {
    final icon = file.isFolder
      ? Icons.folder_outlined
      : Icons.insert_drive_file_outlined;
    final color = file.isFolder ? RapidColors.accent : RapidColors.textSecondary;

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      leading: Icon(icon, color: color, size: 20),
      title: Text(file.name,
        style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
        maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: file.isFolder
        ? null
        : Text(_formatSize(file.size), style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
      trailing: file.isFolder
        ? const Icon(Icons.chevron_right, color: RapidColors.textSecondary, size: 18)
        : importing
          ? const SizedBox(width: 18, height: 18,
              child: CircularProgressIndicator(strokeWidth: 2, color: RapidColors.accent))
          : TextButton(
              onPressed: onImport,
              child: const Text('Import', style: TextStyle(fontSize: 12, color: RapidColors.accent)),
            ),
    );
  }

  String _formatSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
