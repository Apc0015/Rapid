import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:file_picker/file_picker.dart';
import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../theme.dart';
import '../widgets/dept_badge.dart';
import 'dept_settings_screen.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  Map<String, dynamic>? _health;
  Map<String, dynamic>? _stats;
  bool _loadingHealth = true;
  bool _loadingStats  = true;
  String? _healthError;
  String? _statsError;

  // Upload form state
  String _ingestDept = 'hr';
  bool _ingesting = false;
  String? _ingestResult;
  String? _ingestError;
  String? _pickedFileName;
  Uint8List? _pickedFileBytes;

  // LLM config state
  String _llmProvider = 'anthropic';
  bool _llmConfiguring = false;
  bool _llmFetchingModels = false;
  String? _llmResult;
  String? _llmError;
  Map<String, dynamic>? _llmStatus;
  List<String> _availableModels = [];
  String? _selectedModel;
  final _llmKeyCtrl      = TextEditingController();
  final _ollamaUrlCtrl   = TextEditingController(text: 'http://localhost:11434');
  bool _llmKeyVisible = false;

  // DB connection form state
  String _dbType = 'sqlite';
  bool _dbConnecting = false;
  String? _dbResult;
  String? _dbError;
  Map<String, dynamic>? _dbConnections;
  bool _loadingDbConns = false;
  final _dbPathCtrl   = TextEditingController();
  final _dbHostCtrl   = TextEditingController();
  final _dbPortCtrl   = TextEditingController(text: '5432');
  final _dbNameCtrl   = TextEditingController();
  final _dbUserCtrl   = TextEditingController();
  final _dbPassCtrl   = TextEditingController();
  final _dbLabelCtrl  = TextEditingController();
  bool _dbPassVisible = false;

  final List<String> _allDepts = [
    'hr', 'finance', 'legal', 'sales', 'marketing',
    'ops', 'it', 'procurement', 'rd', 'customer_success',
  ];

  @override
  void initState() {
    super.initState();
    _loadHealth();
    _loadStats();
    _loadDbConnections();
    _loadLlmStatus();
  }

  Future<void> _pickFile() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['txt', 'pdf', 'md', 'csv', 'json'],
      withData: true,
    );
    if (result != null && result.files.isNotEmpty) {
      final f = result.files.first;
      setState(() {
        _pickedFileName  = f.name;
        _pickedFileBytes = f.bytes;
        _ingestResult    = null;
        _ingestError     = null;
      });
    }
  }

  @override
  void dispose() {
    _dbPathCtrl.dispose();
    _dbHostCtrl.dispose();
    _dbPortCtrl.dispose();
    _dbNameCtrl.dispose();
    _dbUserCtrl.dispose();
    _dbPassCtrl.dispose();
    _dbLabelCtrl.dispose();
    _llmKeyCtrl.dispose();
    _ollamaUrlCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadHealth() async {
    setState(() { _loadingHealth = true; _healthError = null; });
    try {
      final h = await ApiService.health();
      setState(() { _health = h; _loadingHealth = false; });
    } catch (e) {
      setState(() { _healthError = e.toString().replaceFirst('Exception: ', ''); _loadingHealth = false; });
    }
  }

  Future<void> _loadStats() async {
    final auth = context.read<AuthProvider>();
    setState(() { _loadingStats = true; _statsError = null; });
    try {
      final s = await ApiService.agentStats(userId: auth.userId!, password: auth.password!);
      setState(() { _stats = s; _loadingStats = false; });
    } catch (e) {
      setState(() { _statsError = e.toString().replaceFirst('Exception: ', ''); _loadingStats = false; });
    }
  }

  Future<void> _loadLlmStatus() async {
    final auth = context.read<AuthProvider>();
    try {
      final s = await ApiService.llmStatus(userId: auth.userId!, password: auth.password!);
      setState(() => _llmStatus = s);
    } catch (_) {}
  }

  Future<void> _fetchModels() async {
    final auth = context.read<AuthProvider>();
    final isOllama = _llmProvider == 'ollama';
    final key = _llmKeyCtrl.text.trim();
    if (!isOllama && key.isEmpty) {
      setState(() => _llmError = 'Enter your API key first, then fetch models.');
      return;
    }
    setState(() { _llmFetchingModels = true; _llmError = null; _availableModels = []; _selectedModel = null; });
    try {
      final models = await ApiService.llmModels(
        userId:    auth.userId!,
        password:  auth.password!,
        provider:  _llmProvider,
        apiKey:    key,
        ollamaUrl: isOllama ? _ollamaUrlCtrl.text.trim() : '',
      );
      setState(() {
        _availableModels    = models;
        _selectedModel      = models.isNotEmpty ? models.first : null;
        _llmFetchingModels  = false;
        if (models.isEmpty) _llmError = 'No models found. Is Ollama running?';
      });
    } catch (e) {
      setState(() {
        _llmError          = e.toString().replaceFirst('Exception: ', '');
        _llmFetchingModels = false;
      });
    }
  }

  Future<void> _configureLlm() async {
    final isOllama = _llmProvider == 'ollama';
    if (!isOllama && _llmKeyCtrl.text.trim().isEmpty) {
      setState(() => _llmError = 'Please enter an API key.');
      return;
    }
    if (isOllama && _ollamaUrlCtrl.text.trim().isEmpty) {
      setState(() => _llmError = 'Please enter the Ollama URL.');
      return;
    }
    final auth = context.read<AuthProvider>();
    setState(() { _llmConfiguring = true; _llmResult = null; _llmError = null; });
    try {
      final result = await ApiService.llmConfigure(
        userId:      auth.userId!,
        password:    auth.password!,
        provider:    _llmProvider,
        apiKey:      isOllama ? null : _llmKeyCtrl.text.trim(),
        model:       _selectedModel,
        ollamaUrl:   isOllama ? _ollamaUrlCtrl.text.trim() : null,
        ollamaModel: isOllama ? _selectedModel : null,
      );
      setState(() {
        _llmResult      = result['message'] ?? '✓ Configured';
        _llmConfiguring = false;
        if (!isOllama) _llmKeyCtrl.clear();
      });
      _loadLlmStatus();
    } catch (e) {
      setState(() {
        _llmError       = e.toString().replaceFirst('Exception: ', '');
        _llmConfiguring = false;
      });
    }
  }

  Future<void> _loadDbConnections() async {
    final auth = context.read<AuthProvider>();
    setState(() => _loadingDbConns = true);
    try {
      final conns = await ApiService.dbConnections(userId: auth.userId!, password: auth.password!);
      setState(() { _dbConnections = conns; _loadingDbConns = false; });
    } catch (e) {
      setState(() { _loadingDbConns = false; });
    }
  }

  Future<void> _connectDb() async {
    final auth = context.read<AuthProvider>();
    setState(() { _dbConnecting = true; _dbResult = null; _dbError = null; });
    try {
      final result = await ApiService.dbConnect(
        userId:     auth.userId!,
        password:   auth.password!,
        dbType:     _dbType,
        dbPath:     _dbType == 'sqlite' ? _dbPathCtrl.text.trim() : null,
        host:       _dbType != 'sqlite' ? _dbHostCtrl.text.trim() : null,
        port:       _dbType != 'sqlite' ? int.tryParse(_dbPortCtrl.text.trim()) : null,
        database:   _dbType != 'sqlite' ? _dbNameCtrl.text.trim() : null,
        username:   _dbType != 'sqlite' ? _dbUserCtrl.text.trim() : null,
        dbPassword: _dbType != 'sqlite' ? _dbPassCtrl.text.trim() : null,
        label:    _dbLabelCtrl.text.trim().isNotEmpty ? _dbLabelCtrl.text.trim() : null,
      );
      setState(() {
        _dbResult     = '✓ Connection "${result['connection_id']}" registered (${result['status']})';
        _dbConnecting = false;
      });
      _loadDbConnections(); // refresh connections list
    } catch (e) {
      setState(() {
        _dbError      = e.toString().replaceFirst('Exception: ', '');
        _dbConnecting = false;
      });
    }
  }

  Future<void> _ingest() async {
    if (_pickedFileBytes == null || _pickedFileName == null) {
      setState(() => _ingestError = 'Please select a file first.');
      return;
    }
    final auth = context.read<AuthProvider>();
    setState(() { _ingesting = true; _ingestResult = null; _ingestError = null; });
    try {
      final result = await ApiService.uploadFile(
        userId:    auth.userId!,
        password:  auth.password!,
        deptTag:   _ingestDept,
        fileName:  _pickedFileName!,
        fileBytes: _pickedFileBytes!,
      );
      setState(() {
        _ingestResult    = '✓ Ingested ${result['chunks_created']} chunks from "${result['file']}"';
        _pickedFileName  = null;
        _pickedFileBytes = null;
        _ingesting       = false;
      });
    } catch (e) {
      setState(() {
        _ingestError = e.toString().replaceFirst('Exception: ', '');
        _ingesting   = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: RapidColors.primary,
      appBar: AppBar(
        title: const Text('Admin Panel'),
        backgroundColor: RapidColors.surface,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: RapidColors.textSecondary),
          onPressed: () => Navigator.pop(context),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: RapidColors.textSecondary),
            onPressed: () { _loadHealth(); _loadStats(); },
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // System health
            _SectionHeader(title: 'System Health', onRefresh: _loadHealth),
            const SizedBox(height: 12),
            _loadingHealth
              ? _loadingCard()
              : _healthError != null
                ? _errorCard(_healthError!)
                : _HealthCard(health: _health!),
            const SizedBox(height: 28),

            // Agent stats
            _SectionHeader(title: 'Agent Performance', onRefresh: _loadStats),
            const SizedBox(height: 12),
            _loadingStats
              ? _loadingCard()
              : _statsError != null
                ? _errorCard(_statsError!)
                : _AgentStatsGrid(stats: _stats!),
            const SizedBox(height: 28),

            // Document ingest
            const _SectionHeader(title: 'Upload Document to RAG'),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: RapidColors.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: RapidColors.divider),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Upload a document (.txt, .pdf, .md, .csv, .json) and it will be ingested into the RAG index for the selected department.',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 13),
                  ),
                  const SizedBox(height: 20),

                  // File drop zone / picker
                  GestureDetector(
                    onTap: _ingesting ? null : _pickFile,
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 20),
                      decoration: BoxDecoration(
                        color: _pickedFileName != null
                          ? RapidColors.accent.withOpacity(0.08)
                          : RapidColors.surfaceAlt,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: _pickedFileName != null
                            ? RapidColors.accent.withOpacity(0.5)
                            : RapidColors.divider,
                          width: _pickedFileName != null ? 1.5 : 1,
                        ),
                      ),
                      child: Column(
                        children: [
                          Icon(
                            _pickedFileName != null ? Icons.insert_drive_file_outlined : Icons.cloud_upload_outlined,
                            color: _pickedFileName != null ? RapidColors.accent : RapidColors.textSecondary,
                            size: 36,
                          ),
                          const SizedBox(height: 10),
                          if (_pickedFileName != null) ...[
                            Text(
                              _pickedFileName!,
                              style: const TextStyle(color: RapidColors.accent, fontWeight: FontWeight.w600, fontSize: 14),
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '${(_pickedFileBytes!.length / 1024).toStringAsFixed(1)} KB  •  tap to change',
                              style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
                            ),
                          ] else ...[
                            const Text('Click to select a file', style: TextStyle(color: RapidColors.textPrimary, fontSize: 14)),
                            const SizedBox(height: 4),
                            const Text('.txt  .pdf  .md  .csv  .json', style: TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                          ],
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Department selector
                  Row(
                    children: [
                      const Text('Department:', style: TextStyle(color: RapidColors.textSecondary, fontSize: 13)),
                      const SizedBox(width: 12),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        decoration: BoxDecoration(
                          color: RapidColors.surfaceAlt,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: RapidColors.divider),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<String>(
                            value: _ingestDept,
                            dropdownColor: RapidColors.surface,
                            style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                            items: _allDepts.map((d) => DropdownMenuItem(
                              value: d,
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(deptEmoji[d] ?? '', style: const TextStyle(fontSize: 15)),
                                  const SizedBox(width: 8),
                                  Text(deptLabel[d] ?? d, style: const TextStyle(color: RapidColors.textPrimary)),
                                ],
                              ),
                            )).toList(),
                            onChanged: (v) => setState(() => _ingestDept = v ?? 'hr'),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),

                  // Success / error banners
                  if (_ingestResult != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        color: RapidColors.success.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: RapidColors.success.withOpacity(0.4)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.check_circle_outline, color: RapidColors.success, size: 18),
                          const SizedBox(width: 8),
                          Expanded(child: Text(_ingestResult!, style: const TextStyle(color: RapidColors.success, fontSize: 13))),
                        ],
                      ),
                    ),
                  if (_ingestError != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        color: RapidColors.error.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: RapidColors.error.withOpacity(0.4)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, color: RapidColors.error, size: 18),
                          const SizedBox(width: 8),
                          Expanded(child: Text(_ingestError!, style: const TextStyle(color: RapidColors.error, fontSize: 13))),
                        ],
                      ),
                    ),

                  // Upload button
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      icon: _ingesting
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.cloud_upload_outlined, size: 18),
                      label: Text(_ingesting ? 'Uploading & ingesting…' : 'Upload & Ingest'),
                      onPressed: (_ingesting || _pickedFileName == null) ? null : _ingest,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _pickedFileName != null ? RapidColors.accent : RapidColors.divider,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 28),

            // ── Database connections ─────────────────────────────────────────
            _SectionHeader(title: 'Database Connections', onRefresh: _loadDbConnections),
            const SizedBox(height: 12),

            // Existing connections list
            if (_loadingDbConns)
              _loadingCard()
            else if (_dbConnections != null && _dbConnections!.isNotEmpty)
              Container(
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: RapidColors.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: RapidColors.divider),
                ),
                child: Column(
                  children: _dbConnections!.entries.map((e) {
                    final conn = e.value as Map<String, dynamic>;
                    final isOk = conn['status'] == 'connected';
                    return ListTile(
                      leading: Icon(
                        _dbIcon(conn['type'] as String? ?? ''),
                        color: RapidColors.accent, size: 20,
                      ),
                      title: Text(
                        conn['label'] as String? ?? e.key,
                        style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13, fontWeight: FontWeight.w600),
                      ),
                      subtitle: Text(
                        _dbSubtitle(conn),
                        style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11),
                      ),
                      trailing: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: (isOk ? RapidColors.success : RapidColors.warning).withOpacity(0.15),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          conn['status'] as String? ?? 'unknown',
                          style: TextStyle(
                            color: isOk ? RapidColors.success : RapidColors.warning,
                            fontSize: 11, fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ),

            // Add connection form
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: RapidColors.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: RapidColors.divider),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Add Database Connection',
                    style: TextStyle(color: RapidColors.textPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  const Text(
                    'Connect a read-only database. Queries will be answered using both documents and live data.',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 12),
                  ),
                  const SizedBox(height: 20),

                  // DB type selector
                  Row(
                    children: ['sqlite', 'postgresql', 'mysql'].map((t) => Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: Text(t),
                        selected: _dbType == t,
                        selectedColor: RapidColors.accent.withOpacity(0.25),
                        backgroundColor: RapidColors.surfaceAlt,
                        labelStyle: TextStyle(
                          color: _dbType == t ? RapidColors.accent : RapidColors.textSecondary,
                          fontSize: 12,
                        ),
                        side: BorderSide(
                          color: _dbType == t ? RapidColors.accent.withOpacity(0.6) : RapidColors.divider,
                        ),
                        onSelected: (_) => setState(() { _dbType = t; _dbResult = null; _dbError = null; }),
                      ),
                    )).toList(),
                  ),
                  const SizedBox(height: 16),

                  // Label
                  _DbField(controller: _dbLabelCtrl, label: 'Connection label (optional)', hint: 'e.g. Sales DB'),
                  const SizedBox(height: 12),

                  // SQLite fields
                  if (_dbType == 'sqlite') ...[
                    _DbField(controller: _dbPathCtrl, label: 'SQLite file path', hint: 'e.g. data/sales.db'),
                  ],

                  // PostgreSQL / MySQL fields
                  if (_dbType != 'sqlite') ...[
                    Row(
                      children: [
                        Expanded(flex: 3, child: _DbField(controller: _dbHostCtrl, label: 'Host', hint: 'localhost')),
                        const SizedBox(width: 10),
                        Expanded(flex: 1, child: _DbField(controller: _dbPortCtrl, label: 'Port', hint: _dbType == 'mysql' ? '3306' : '5432', keyboardType: TextInputType.number)),
                      ],
                    ),
                    const SizedBox(height: 12),
                    _DbField(controller: _dbNameCtrl, label: 'Database name', hint: 'my_database'),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(child: _DbField(controller: _dbUserCtrl, label: 'Username', hint: 'db_user')),
                        const SizedBox(width: 10),
                        Expanded(
                          child: TextField(
                            controller: _dbPassCtrl,
                            obscureText: !_dbPassVisible,
                            style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                            decoration: InputDecoration(
                              labelText: 'Password',
                              labelStyle: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
                              hintText: '••••••••',
                              hintStyle: const TextStyle(color: RapidColors.textSecondary),
                              filled: true,
                              fillColor: RapidColors.surfaceAlt,
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                                borderSide: const BorderSide(color: RapidColors.divider),
                              ),
                              enabledBorder: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                                borderSide: const BorderSide(color: RapidColors.divider),
                              ),
                              focusedBorder: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                                borderSide: BorderSide(color: RapidColors.accent.withOpacity(0.6)),
                              ),
                              isDense: true,
                              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                              suffixIcon: IconButton(
                                icon: Icon(
                                  _dbPassVisible ? Icons.visibility_off : Icons.visibility,
                                  color: RapidColors.textSecondary, size: 18,
                                ),
                                onPressed: () => setState(() => _dbPassVisible = !_dbPassVisible),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 20),

                  // Result banners
                  if (_dbResult != null)
                    _StatusBanner(message: _dbResult!, isSuccess: true),
                  if (_dbError != null)
                    _StatusBanner(message: _dbError!, isSuccess: false),

                  // Connect button
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      icon: _dbConnecting
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.cable_outlined, size: 18),
                      label: Text(_dbConnecting ? 'Testing connection…' : 'Test & Connect'),
                      onPressed: _dbConnecting ? null : _connectDb,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: RapidColors.accent,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 28),

            // ── LLM Configuration ────────────────────────────────────────────
            const _SectionHeader(title: 'LLM Configuration'),
            const SizedBox(height: 12),

            // Status pills
            if (_llmStatus != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Wrap(
                  spacing: 8, runSpacing: 8,
                  children: _llmStatus!.entries.map((e) {
                    final ok = e.value == true;
                    return Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: (ok ? RapidColors.success : RapidColors.divider).withOpacity(0.15),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: ok ? RapidColors.success.withOpacity(0.4) : RapidColors.divider),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(ok ? Icons.check_circle_outline : Icons.radio_button_unchecked,
                            color: ok ? RapidColors.success : RapidColors.textSecondary, size: 14),
                          const SizedBox(width: 6),
                          Text(e.key[0].toUpperCase() + e.key.substring(1),
                            style: TextStyle(
                              color: ok ? RapidColors.success : RapidColors.textSecondary,
                              fontSize: 12, fontWeight: FontWeight.w600,
                            )),
                        ],
                      ),
                    );
                  }).toList(),
                ),
              ),

            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: RapidColors.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: RapidColors.divider),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Set API Key',
                    style: TextStyle(color: RapidColors.textPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  const Text(
                    'The key is saved to the server .env file and applied immediately — no restart needed.',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 12),
                  ),
                  const SizedBox(height: 16),

                  // ── Step 1: Provider selector ──────────────────────────
                  const Text('Step 1 — Choose provider',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8, runSpacing: 8,
                    children: [
                      {'id': 'anthropic',  'label': 'Anthropic'},
                      {'id': 'openrouter', 'label': 'OpenRouter'},
                      {'id': 'openai',     'label': 'OpenAI'},
                      {'id': 'ollama',     'label': '🦙 Ollama (Local)'},
                    ].map((p) => ChoiceChip(
                      label: Text(p['label']!),
                      selected: _llmProvider == p['id'],
                      selectedColor: RapidColors.accent.withOpacity(0.12),
                      backgroundColor: RapidColors.surfaceAlt,
                      labelStyle: TextStyle(
                        color: _llmProvider == p['id'] ? RapidColors.accent : RapidColors.textSecondary,
                        fontSize: 12, fontWeight: FontWeight.w500,
                      ),
                      side: BorderSide(
                        color: _llmProvider == p['id'] ? RapidColors.accent : RapidColors.divider,
                      ),
                      onSelected: (_) => setState(() {
                        _llmProvider = p['id']!;
                        _llmResult = null; _llmError = null;
                        _availableModels = []; _selectedModel = null;
                      }),
                    )).toList(),
                  ),
                  const SizedBox(height: 20),

                  // ── Step 2: Key / URL input + Fetch Models ─────────────
                  const Text('Step 2 — Enter credentials & fetch models',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 8),

                  if (_llmProvider == 'ollama') ...[
                    _DbField(
                      controller: _ollamaUrlCtrl,
                      label: 'Ollama base URL',
                      hint: 'http://localhost:11434',
                    ),
                    const SizedBox(height: 4),
                    const Text('Make sure Ollama is running:  ollama serve',
                      style: TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
                  ] else ...[
                    // API key + show/hide + fetch button in one row
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _llmKeyCtrl,
                            obscureText: !_llmKeyVisible,
                            style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                            decoration: InputDecoration(
                              labelText: _llmProvider == 'anthropic'
                                ? 'Anthropic API Key (sk-ant-...)'
                                : _llmProvider == 'openrouter'
                                  ? 'OpenRouter Key (sk-or-...)'
                                  : 'OpenAI Key (sk-...)',
                              labelStyle: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
                              hintText: 'Paste your API key',
                              hintStyle: const TextStyle(color: RapidColors.textSecondary),
                              filled: true,
                              fillColor: RapidColors.surfaceAlt,
                              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
                              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
                              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent, width: 1.5)),
                              isDense: true,
                              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                              suffixIcon: IconButton(
                                icon: Icon(_llmKeyVisible ? Icons.visibility_off : Icons.visibility, color: RapidColors.textSecondary, size: 16),
                                onPressed: () => setState(() => _llmKeyVisible = !_llmKeyVisible),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 10),

                  // Fetch models button
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      icon: _llmFetchingModels
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: RapidColors.accent))
                        : const Icon(Icons.search_rounded, size: 16, color: RapidColors.accent),
                      label: Text(
                        _llmFetchingModels ? 'Detecting models…' : 'Detect Available Models',
                        style: const TextStyle(color: RapidColors.accent, fontSize: 13),
                      ),
                      onPressed: _llmFetchingModels ? null : _fetchModels,
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: RapidColors.accent),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                    ),
                  ),

                  // ── Step 3: Model picker (shown after fetch) ───────────
                  if (_availableModels.isNotEmpty) ...[
                    const SizedBox(height: 20),
                    const Text('Step 3 — Select model',
                      style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      decoration: BoxDecoration(
                        color: RapidColors.surfaceAlt,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: RapidColors.divider),
                      ),
                      child: DropdownButtonHideUnderline(
                        child: DropdownButton<String>(
                          value: _selectedModel,
                          isExpanded: true,
                          dropdownColor: RapidColors.surface,
                          style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                          icon: const Icon(Icons.expand_more, color: RapidColors.textSecondary, size: 18),
                          items: _availableModels.map((m) => DropdownMenuItem(
                            value: m,
                            child: Text(m, overflow: TextOverflow.ellipsis,
                              style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13)),
                          )).toList(),
                          onChanged: (v) => setState(() => _selectedModel = v),
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text('${_availableModels.length} model${_availableModels.length != 1 ? 's' : ''} available',
                      style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
                  ],

                  const SizedBox(height: 16),
                  if (_llmResult != null) _StatusBanner(message: _llmResult!, isSuccess: true),
                  if (_llmError  != null) _StatusBanner(message: _llmError!,  isSuccess: false),

                  // ── Save button ────────────────────────────────────────
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      icon: _llmConfiguring
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.check_circle_outline, size: 18),
                      label: Text(_llmConfiguring
                        ? 'Saving…'
                        : _selectedModel != null
                          ? 'Save — $_selectedModel'
                          : (_llmProvider == 'ollama' ? 'Save Ollama Config' : 'Save API Key')),
                      onPressed: (_llmConfiguring || (_availableModels.isNotEmpty && _selectedModel == null)) ? null : _configureLlm,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: RapidColors.accent,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),

            // ── Per-Department Settings ──────────────────────────────────────
            _SectionHeader(
              title: 'Per-Department Settings',
              action: TextButton.icon(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const DeptSettingsScreen()),
                ),
                icon: const Icon(Icons.tune, size: 16, color: RapidColors.accent),
                label: const Text('Open', style: TextStyle(color: RapidColors.accent, fontSize: 13)),
              ),
            ),
            const SizedBox(height: 12),
            _DeptSettingsPreview(onOpen: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const DeptSettingsScreen()),
            )),
            const SizedBox(height: 32),

            // ── Dept Head Assignment ─────────────────────────────────────────
            const _SectionHeader(title: 'Department Head Assignment'),
            const SizedBox(height: 12),
            const _DeptHeadPanel(),
            const SizedBox(height: 32),

            // ── Division / C-Suite Assignment ────────────────────────────────
            const _SectionHeader(title: 'Division & C-Suite Assignment'),
            const SizedBox(height: 12),
            const _DivisionPanel(),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  IconData _dbIcon(String type) {
    switch (type) {
      case 'postgresql': return Icons.storage_rounded;
      case 'mysql': return Icons.table_chart_outlined;
      default: return Icons.dataset_outlined;
    }
  }

  String _dbSubtitle(Map<String, dynamic> conn) {
    final type = conn['type'] as String? ?? '';
    if (type == 'sqlite') return 'SQLite • ${conn['path'] ?? ''}';
    final host = conn['host'] ?? '';
    final port = conn['port'] ?? '';
    final db   = conn['database'] ?? '';
    return '${type.toUpperCase()} • $host:$port/$db';
  }

  Widget _loadingCard() => Container(
    height: 80,
    decoration: BoxDecoration(color: RapidColors.surface, borderRadius: BorderRadius.circular(12)),
    child: const Center(child: CircularProgressIndicator(color: RapidColors.accent)),
  );

  Widget _errorCard(String msg) => Container(
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: RapidColors.error.withOpacity(0.1),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: RapidColors.error.withOpacity(0.4)),
    ),
    child: Text(msg, style: const TextStyle(color: RapidColors.error, fontSize: 13)),
  );
}

// ── Reusable form field for DB connection ──────────────────────────────────────
class _DbField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  final TextInputType keyboardType;
  const _DbField({
    required this.controller,
    required this.label,
    required this.hint,
    this.keyboardType = TextInputType.text,
  });

  @override
  Widget build(BuildContext context) => TextField(
    controller: controller,
    keyboardType: keyboardType,
    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
    decoration: InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
      hintText: hint,
      hintStyle: const TextStyle(color: RapidColors.textSecondary),
      filled: true,
      fillColor: RapidColors.surfaceAlt,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: RapidColors.divider),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: RapidColors.divider),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: RapidColors.accent.withOpacity(0.6)),
      ),
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
    ),
  );
}

// ── Success / error banner ─────────────────────────────────────────────────────
class _StatusBanner extends StatelessWidget {
  final String message;
  final bool isSuccess;
  const _StatusBanner({required this.message, required this.isSuccess});

  @override
  Widget build(BuildContext context) {
    final color = isSuccess ? RapidColors.success : RapidColors.error;
    return Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Row(
        children: [
          Icon(isSuccess ? Icons.check_circle_outline : Icons.error_outline, color: color, size: 18),
          const SizedBox(width: 8),
          Expanded(child: Text(message, style: TextStyle(color: color, fontSize: 13))),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final VoidCallback? onRefresh;
  final Widget? action;
  const _SectionHeader({required this.title, this.onRefresh, this.action});

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Text(title, style: const TextStyle(color: RapidColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w700)),
      if (onRefresh != null) ...[
        const SizedBox(width: 8),
        InkWell(
          onTap: onRefresh,
          borderRadius: BorderRadius.circular(4),
          child: const Icon(Icons.refresh, size: 16, color: RapidColors.textSecondary),
        ),
      ],
      const Spacer(),
      if (action != null) action!,
    ],
  );
}


class _DeptSettingsPreview extends StatelessWidget {
  final VoidCallback onOpen;
  const _DeptSettingsPreview({required this.onOpen});

  static const _depts = ['hr', 'finance', 'legal', 'sales', 'marketing', 'ops', 'it', 'procurement', 'rd', 'customer_success'];

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: RapidColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              'Configure RAG pipeline settings (embedding model, chunk size, HyDE) and database connections independently for each department.',
              style: const TextStyle(color: RapidColors.textSecondary, fontSize: 13),
            ),
          ),
          const Divider(color: RapidColors.divider, height: 1),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _depts.map((d) => _DeptChip(dept: d)).toList(),
            ),
          ),
          const Divider(color: RapidColors.divider, height: 1),
          Padding(
            padding: const EdgeInsets.all(12),
            child: SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: RapidColors.accent,
                  side: const BorderSide(color: RapidColors.accent),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
                onPressed: onOpen,
                icon: const Icon(Icons.tune, size: 16),
                label: const Text('Open Department Settings'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DeptChip extends StatelessWidget {
  final String dept;
  const _DeptChip({required this.dept});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: RapidColors.accent.withOpacity(0.1),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: RapidColors.accent.withOpacity(0.3)),
      ),
      child: Text(dept.toUpperCase(), style: const TextStyle(color: RapidColors.accent, fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }
}

class _HealthCard extends StatelessWidget {
  final Map<String, dynamic> health;
  const _HealthCard({required this.health});

  @override
  Widget build(BuildContext context) {
    final status = health['status'] ?? 'unknown';
    final agents = (health['agents'] as List?)?.cast<String>() ?? [];
    final docs = health['chroma_docs'] ?? 0;
    final schemas = (health['db_schemas_loaded'] as List?)?.length ?? 0;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: RapidColors.divider),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 10, height: 10,
                decoration: BoxDecoration(
                  color: status == 'ok' ? RapidColors.success : RapidColors.error,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Text(status == 'ok' ? 'All systems operational' : 'Status: $status',
                style: TextStyle(
                  color: status == 'ok' ? RapidColors.success : RapidColors.error,
                  fontWeight: FontWeight.w600,
                )),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              _StatTile(label: 'Agents', value: '${agents.length}'),
              const SizedBox(width: 12),
              _StatTile(label: 'Documents indexed', value: '$docs'),
              const SizedBox(width: 12),
              _StatTile(label: 'DB Schemas', value: '$schemas'),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 6, runSpacing: 6,
            children: agents.map((a) => DeptBadge(dept: a)).toList(),
          ),
        ],
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final String label, value;
  const _StatTile({required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Expanded(
    child: Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: RapidColors.surfaceAlt,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: const TextStyle(color: RapidColors.accent, fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
        ],
      ),
    ),
  );
}

class _AgentStatsGrid extends StatelessWidget {
  final Map<String, dynamic> stats;
  const _AgentStatsGrid({required this.stats});

  @override
  Widget build(BuildContext context) {
    if (stats.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: Text('No agent stats yet — run some queries first.', style: TextStyle(color: RapidColors.textSecondary)),
        ),
      );
    }

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 220,
        childAspectRatio: 1.6,
        crossAxisSpacing: 10,
        mainAxisSpacing: 10,
      ),
      itemCount: stats.length,
      itemBuilder: (ctx, i) {
        final dept = stats.keys.elementAt(i);
        final data = stats[dept] as Map<String, dynamic>? ?? {};
        final tasks = data['tasks'] ?? 0;
        final avgConf = (data['avg_confidence'] as num?)?.toDouble();

        Color confColor = RapidColors.textSecondary;
        if (avgConf != null) {
          if (avgConf >= 0.65) confColor = RapidColors.success;
          else if (avgConf >= 0.40) confColor = RapidColors.warning;
          else confColor = RapidColors.error;
        }

        return Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: RapidColors.surface,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: RapidColors.divider),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              DeptBadge(dept: dept),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('$tasks tasks', style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
                  if (avgConf != null)
                    Text('${(avgConf * 100).toStringAsFixed(0)}% avg conf',
                      style: TextStyle(color: confColor, fontSize: 13, fontWeight: FontWeight.w700)),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

// ── Division / C-Suite Assignment Panel ──────────────────────────────────────
class _DivisionPanel extends StatefulWidget {
  const _DivisionPanel();
  @override State<_DivisionPanel> createState() => _DivisionPanelState();
}

class _DivisionPanelState extends State<_DivisionPanel> {
  Map<String, dynamic>? _data;
  List<dynamic> _users = [];
  bool _loading = true;
  bool _acting  = false;
  String? _result;
  String? _error;
  String _selectedDiv    = '';
  String _selectedUserId = '';
  final _titleCtrl = TextEditingController();

  static const List<String> _allDivisions = [
    'commercial', 'finance_div', 'people', 'technology', 'operations',
  ];

  @override
  void initState() { super.initState(); _load(); }

  @override
  void dispose() { _titleCtrl.dispose(); super.dispose(); }

  Future<void> _load() async {
    final auth = context.read<AuthProvider>();
    setState(() { _loading = true; _result = null; _error = null; });
    try {
      final futures = await Future.wait([
        ApiService.getDivisions(userId: auth.userId!, password: auth.password!),
        ApiService.listPortalUsers(userId: auth.userId!, password: auth.password!),
      ]);
      setState(() {
        _data    = futures[0] as Map<String, dynamic>;
        _users   = futures[1] as List<dynamic>;
        _loading = false;
        _selectedDiv    = _allDivisions.first;
        _selectedUserId = _users.isNotEmpty ? (_users.first['rapid_user_id'] as String? ?? '') : '';
      });
    } catch (e) {
      setState(() { _loading = false; _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  Future<void> _assign() async {
    if (_selectedDiv.isEmpty || _selectedUserId.isEmpty) return;
    final auth = context.read<AuthProvider>();
    setState(() { _acting = true; _result = null; _error = null; });
    try {
      await ApiService.setDivisionHead(
        adminId:      auth.userId!,
        password:     auth.password!,
        division:     _selectedDiv,
        targetUserId: _selectedUserId,
        title:        _titleCtrl.text.trim(),
      );
      setState(() { _result = 'Assigned to division "$_selectedDiv".'; _acting = false; });
      _titleCtrl.clear();
      _load();
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _acting = false; });
    }
  }

  Future<void> _remove(String division) async {
    final auth = context.read<AuthProvider>();
    try {
      await ApiService.removeDivisionHead(adminId: auth.userId!, password: auth.password!, division: division);
      _load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(e.toString().replaceFirst('Exception: ', '')),
        backgroundColor: RapidColors.error,
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return Container(
      height: 80, decoration: BoxDecoration(color: RapidColors.surface, borderRadius: BorderRadius.circular(12)),
      child: const Center(child: CircularProgressIndicator(color: RapidColors.accent)),
    );

    final divs = (_data ?? {}) as Map<String, dynamic>;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: RapidColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Assign a C-Suite executive as division head. Division heads review access requests after dept heads, before they reach admin.',
            style: TextStyle(color: RapidColors.textSecondary, fontSize: 12, height: 1.5),
          ),
          const SizedBox(height: 16),

          // Current division assignments
          ...divs.entries.map((e) {
            final info    = e.value as Map<String, dynamic>? ?? {};
            final headId  = info['user_id'] as String?;
            final name    = info['name']    as String? ?? '-';
            final depts   = (info['depts']  as List?)?.cast<String>() ?? [];
            final csTitle = info['csuite_title'] as String? ?? '';

            return Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: RapidColors.surfaceAlt,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: headId != null ? RapidColors.accent.withOpacity(0.3) : RapidColors.divider),
              ),
              child: Row(children: [
                Icon(
                  headId != null ? Icons.business_center_outlined : Icons.radio_button_unchecked,
                  color: headId != null ? RapidColors.accent : RapidColors.textSecondary,
                  size: 18,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Text(e.key, style: const TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w600, fontSize: 13)),
                      const SizedBox(width: 8),
                      Text('($csTitle)', style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
                    ]),
                    const SizedBox(height: 2),
                    Text(depts.join(', '), style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
                    if (headId != null) ...[
                      const SizedBox(height: 2),
                      Text('→  $name ($headId)', style: const TextStyle(color: RapidColors.accent, fontSize: 12, fontWeight: FontWeight.w500)),
                    ],
                  ]),
                ),
                if (headId != null)
                  IconButton(
                    icon: const Icon(Icons.remove_circle_outline, color: RapidColors.error, size: 18),
                    tooltip: 'Remove',
                    constraints: const BoxConstraints(),
                    padding: EdgeInsets.zero,
                    onPressed: () => _remove(e.key),
                  ),
              ]),
            );
          }),

          const SizedBox(height: 16),
          const Divider(color: RapidColors.divider),
          const SizedBox(height: 12),
          const Text('Assign division head:',
            style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),

          // Division picker
          _dropdown(
            value: _selectedDiv.isNotEmpty ? _selectedDiv : null,
            hint: 'Division',
            items: _allDivisions.map((d) => DropdownMenuItem(value: d, child: Text(d))).toList(),
            onChanged: (v) => setState(() => _selectedDiv = v ?? ''),
          ),
          const SizedBox(height: 8),

          // User picker
          _dropdown(
            value: _selectedUserId.isNotEmpty ? _selectedUserId : null,
            hint: 'User',
            items: _users.map((u) {
              final uid  = u['rapid_user_id'] as String? ?? '';
              final name = u['name'] as String? ?? uid;
              return DropdownMenuItem(value: uid, child: Text(name, overflow: TextOverflow.ellipsis));
            }).toList(),
            onChanged: (v) => setState(() => _selectedUserId = v ?? ''),
          ),
          const SizedBox(height: 8),

          // Optional title override
          TextField(
            controller: _titleCtrl,
            style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
            decoration: InputDecoration(
              labelText: 'Title override (optional, e.g. "CFO")',
              labelStyle: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
              filled: true, fillColor: RapidColors.surfaceAlt,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent)),
              isDense: true, contentPadding: const EdgeInsets.all(12),
            ),
          ),
          const SizedBox(height: 12),

          if (_result != null) _StatusBanner(message: _result!, isSuccess: true),
          if (_error  != null) _StatusBanner(message: _error!,  isSuccess: false),

          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              icon: _acting
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.corporate_fare_outlined, size: 18),
              label: Text(_acting ? 'Assigning…' : 'Assign Division Head'),
              onPressed: (_acting || _selectedDiv.isEmpty || _selectedUserId.isEmpty) ? null : _assign,
              style: ElevatedButton.styleFrom(
                backgroundColor: RapidColors.accent,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _dropdown<T>({
    required T? value,
    required String hint,
    required List<DropdownMenuItem<T>> items,
    required void Function(T?) onChanged,
  }) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10),
    decoration: BoxDecoration(
      color: RapidColors.surfaceAlt,
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: RapidColors.divider),
    ),
    child: DropdownButtonHideUnderline(
      child: DropdownButton<T>(
        value: value,
        isExpanded: true,
        dropdownColor: RapidColors.surface,
        style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
        hint: Text(hint, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
        items: items,
        onChanged: onChanged,
      ),
    ),
  );
}

// ── Dept Head Assignment Panel ────────────────────────────────────────────────
class _DeptHeadPanel extends StatefulWidget {
  const _DeptHeadPanel();
  @override State<_DeptHeadPanel> createState() => _DeptHeadPanelState();
}

class _DeptHeadPanelState extends State<_DeptHeadPanel> {
  Map<String, dynamic>? _data;
  List<dynamic> _users = [];
  bool _loading = true;
  bool _acting  = false;
  String? _result;
  String? _error;

  String _selectedDept   = '';
  String _selectedUserId = '';

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    final auth = context.read<AuthProvider>();
    setState(() { _loading = true; _result = null; _error = null; });
    try {
      final futures = await Future.wait([
        ApiService.listDeptHeads(userId: auth.userId!, password: auth.password!),
        ApiService.listPortalUsers(userId: auth.userId!, password: auth.password!),
      ]);
      final dh    = futures[0] as Map<String, dynamic>;
      final users = futures[1] as List<dynamic>;
      setState(() {
        _data     = dh;
        _users    = users;
        _loading  = false;
        final allDepts = (dh['all_depts'] as List?)?.cast<String>() ?? [];
        _selectedDept   = allDepts.isNotEmpty ? allDepts.first : '';
        _selectedUserId = users.isNotEmpty ? (users.first['rapid_user_id'] as String? ?? '') : '';
      });
    } catch (e) {
      setState(() { _loading = false; _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  Future<void> _assign() async {
    if (_selectedDept.isEmpty || _selectedUserId.isEmpty) return;
    final auth = context.read<AuthProvider>();
    setState(() { _acting = true; _result = null; _error = null; });
    try {
      await ApiService.assignDeptHead(
        adminId:      auth.userId!,
        password:     auth.password!,
        dept:         _selectedDept,
        targetUserId: _selectedUserId,
      );
      setState(() { _result = 'Assigned $_selectedUserId as head of $_selectedDept.'; _acting = false; });
      _load();
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _acting = false; });
    }
  }

  Future<void> _remove(String dept) async {
    final auth = context.read<AuthProvider>();
    try {
      await ApiService.removeDeptHead(adminId: auth.userId!, password: auth.password!, dept: dept);
      _load();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(e.toString().replaceFirst('Exception: ', '')),
        backgroundColor: RapidColors.error,
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return Container(
      height: 80, decoration: BoxDecoration(color: RapidColors.surface, borderRadius: BorderRadius.circular(12)),
      child: const Center(child: CircularProgressIndicator(color: RapidColors.accent)),
    );

    final heads   = (_data?['dept_heads'] as Map<String, dynamic>?) ?? {};
    final allDepts = (_data?['all_depts'] as List?)?.cast<String>() ?? [];

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: RapidColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Assign a user as department head. Dept heads review access requests from their department before they reach the admin.',
            style: TextStyle(color: RapidColors.textSecondary, fontSize: 12, height: 1.5),
          ),
          const SizedBox(height: 16),

          // Current assignments
          if (heads.isNotEmpty) ...[
            const Text('Current assignments:',
              style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            ...heads.entries.map((e) {
              final info = e.value as Map<String, dynamic>? ?? {};
              return Container(
                margin: const EdgeInsets.only(bottom: 6),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                decoration: BoxDecoration(
                  color: RapidColors.surfaceAlt,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: RapidColors.divider),
                ),
                child: Row(children: [
                  const Icon(Icons.person_outline, color: RapidColors.accent, size: 16),
                  const SizedBox(width: 8),
                  Expanded(child: Text(
                    '${e.key}  →  ${info['name'] ?? e.value}',
                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                  )),
                  IconButton(
                    icon: const Icon(Icons.remove_circle_outline, color: RapidColors.error, size: 18),
                    tooltip: 'Remove assignment',
                    constraints: const BoxConstraints(),
                    padding: EdgeInsets.zero,
                    onPressed: () => _remove(e.key),
                  ),
                ]),
              );
            }),
            const SizedBox(height: 16),
            const Divider(color: RapidColors.divider),
            const SizedBox(height: 12),
          ],

          // Assign form
          const Text('Assign new dept head:',
            style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
          Row(children: [
            // Dept picker
            Expanded(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10),
                decoration: BoxDecoration(
                  color: RapidColors.surfaceAlt,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: RapidColors.divider),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: _selectedDept.isNotEmpty ? _selectedDept : null,
                    isExpanded: true,
                    dropdownColor: RapidColors.surface,
                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                    hint: const Text('Department', style: TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                    items: allDepts.map((d) => DropdownMenuItem(value: d, child: Text(d))).toList(),
                    onChanged: (v) => setState(() => _selectedDept = v ?? ''),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 10),
            // User picker
            Expanded(
              flex: 2,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10),
                decoration: BoxDecoration(
                  color: RapidColors.surfaceAlt,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: RapidColors.divider),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: _selectedUserId.isNotEmpty ? _selectedUserId : null,
                    isExpanded: true,
                    dropdownColor: RapidColors.surface,
                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                    hint: const Text('User', style: TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                    items: _users.map((u) {
                      final uid  = u['rapid_user_id'] as String? ?? '';
                      final name = u['name']          as String? ?? uid;
                      return DropdownMenuItem(value: uid, child: Text(name, overflow: TextOverflow.ellipsis));
                    }).toList(),
                    onChanged: (v) => setState(() => _selectedUserId = v ?? ''),
                  ),
                ),
              ),
            ),
          ]),
          const SizedBox(height: 12),

          if (_result != null) _StatusBanner(message: _result!, isSuccess: true),
          if (_error  != null) _StatusBanner(message: _error!,  isSuccess: false),

          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              icon: _acting
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.person_add_outlined, size: 18),
              label: Text(_acting ? 'Assigning…' : 'Assign Dept Head'),
              onPressed: (_acting || _selectedDept.isEmpty || _selectedUserId.isEmpty) ? null : _assign,
              style: ElevatedButton.styleFrom(
                backgroundColor: RapidColors.accent,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
