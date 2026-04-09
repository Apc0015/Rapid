import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../theme.dart';

/// Per-department settings screen — admin only.
/// Shows RAG pipeline config and DB connection config for a selected department.
class DeptSettingsScreen extends StatefulWidget {
  const DeptSettingsScreen({super.key});

  @override
  State<DeptSettingsScreen> createState() => _DeptSettingsScreenState();
}

class _DeptSettingsScreenState extends State<DeptSettingsScreen> {
  static const _allDepts = [
    'hr', 'finance', 'legal', 'sales', 'marketing',
    'ops', 'it', 'procurement', 'rd', 'customer_success',
  ];

  String _selectedDept = 'hr';
  bool _loading = false;
  String? _error;
  String? _successMsg;

  // RAG config state
  Map<String, dynamic>? _ragConfig;
  bool _ragSaving = false;
  final _chunkSizeCtrl   = TextEditingController();
  final _chunkOverlapCtrl = TextEditingController();
  final _topKCtrl        = TextEditingController();
  final _simThreshCtrl   = TextEditingController();
  final _rrfAlphaCtrl    = TextEditingController();
  final _bm25AlphaCtrl   = TextEditingController();
  String _embeddingModel = 'nomic-embed-text';
  bool _hydeEnabled = true;

  // RAG stats state
  Map<String, dynamic>? _ragStats;
  bool _loadingStats = false;

  // DB config state
  Map<String, dynamic>? _dbConfig;
  bool _dbSaving = false;
  bool _dbTesting = false;
  Map<String, dynamic>? _dbTestResult;
  final _dbPathCtrl = TextEditingController();
  final _dbHostCtrl = TextEditingController();
  final _dbPortCtrl = TextEditingController();
  final _dbNameCtrl = TextEditingController();
  final _dbUserCtrl = TextEditingController();
  final _dbPassCtrl = TextEditingController();
  bool _dbEnabled = false;
  String _dbType = 'sqlite';
  bool _dbPassVisible = false;

  static const _embeddingModels = [
    'nomic-embed-text',
    'all-minilm',
    'mxbai-embed-large',
    'text-embedding-3-small',
    'text-embedding-3-large',
  ];

  @override
  void initState() {
    super.initState();
    _loadDeptConfig();
  }

  @override
  void dispose() {
    _chunkSizeCtrl.dispose();
    _chunkOverlapCtrl.dispose();
    _topKCtrl.dispose();
    _simThreshCtrl.dispose();
    _rrfAlphaCtrl.dispose();
    _bm25AlphaCtrl.dispose();
    _dbPathCtrl.dispose();
    _dbHostCtrl.dispose();
    _dbPortCtrl.dispose();
    _dbNameCtrl.dispose();
    _dbUserCtrl.dispose();
    _dbPassCtrl.dispose();
    super.dispose();
  }

  String get _uid => context.read<AuthProvider>().userId ?? '';
  String get _pw  => context.read<AuthProvider>().password ?? '';

  Future<void> _loadDeptConfig() async {
    setState(() { _loading = true; _error = null; _ragStats = null; _dbTestResult = null; });
    try {
      final rag = await ApiService.getDeptRagConfig(userId: _uid, password: _pw, dept: _selectedDept);
      final db  = await ApiService.getDeptDbConfig(userId: _uid, password: _pw, dept: _selectedDept);
      _applyRagConfig(rag);
      _applyDbConfig(db);
      setState(() { _ragConfig = rag; _dbConfig = db; });
    } catch (e) {
      setState(() { _error = e.toString(); });
    } finally {
      setState(() { _loading = false; });
    }
    _loadRagStats();
  }

  void _applyRagConfig(Map<String, dynamic> c) {
    _chunkSizeCtrl.text    = '${c['chunk_size']    ?? 512}';
    _chunkOverlapCtrl.text = '${c['chunk_overlap'] ?? 64}';
    _topKCtrl.text         = '${c['top_k']         ?? 10}';
    _simThreshCtrl.text    = '${c['similarity_threshold'] ?? 0.25}';
    _rrfAlphaCtrl.text     = '${c['rrf_alpha']  ?? 0.6}';
    _bm25AlphaCtrl.text    = '${c['bm25_alpha'] ?? 0.4}';
    _embeddingModel = c['embedding_model'] ?? 'nomic-embed-text';
    _hydeEnabled    = c['hyde_enabled']    ?? true;
  }

  void _applyDbConfig(Map<String, dynamic> c) {
    _dbEnabled      = c['enabled'] ?? false;
    _dbType         = c['type']    ?? 'sqlite';
    _dbPathCtrl.text = c['path']   ?? '';
    _dbHostCtrl.text = c['host']   ?? '';
    _dbPortCtrl.text = '${c['port'] ?? 5432}';
    _dbNameCtrl.text = c['name']   ?? '';
    _dbUserCtrl.text = c['user']   ?? '';
    _dbPassCtrl.text = '';  // never pre-fill password
  }

  Future<void> _loadRagStats() async {
    setState(() { _loadingStats = true; });
    try {
      final stats = await ApiService.getDeptRagStats(userId: _uid, password: _pw, dept: _selectedDept);
      setState(() { _ragStats = stats; });
    } catch (_) {
      setState(() { _ragStats = null; });
    } finally {
      setState(() { _loadingStats = false; });
    }
  }

  Future<void> _saveRagConfig() async {
    setState(() { _ragSaving = true; _successMsg = null; _error = null; });
    try {
      final updates = <String, dynamic>{
        'embedding_model':      _embeddingModel,
        'chunk_size':           int.tryParse(_chunkSizeCtrl.text) ?? 512,
        'chunk_overlap':        int.tryParse(_chunkOverlapCtrl.text) ?? 64,
        'top_k':                int.tryParse(_topKCtrl.text) ?? 10,
        'similarity_threshold': double.tryParse(_simThreshCtrl.text) ?? 0.25,
        'rrf_alpha':            double.tryParse(_rrfAlphaCtrl.text)  ?? 0.6,
        'bm25_alpha':           double.tryParse(_bm25AlphaCtrl.text) ?? 0.4,
        'hyde_enabled':         _hydeEnabled,
      };
      await ApiService.updateDeptRagConfig(userId: _uid, password: _pw, dept: _selectedDept, updates: updates);
      setState(() { _successMsg = 'RAG config saved for $_selectedDept'; });
    } catch (e) {
      setState(() { _error = e.toString(); });
    } finally {
      setState(() { _ragSaving = false; });
    }
  }

  Future<void> _saveDbConfig() async {
    setState(() { _dbSaving = true; _successMsg = null; _error = null; });
    try {
      final updates = <String, dynamic>{
        'enabled': _dbEnabled,
        'type':    _dbType,
      };
      if (_dbType == 'sqlite') {
        if (_dbPathCtrl.text.isNotEmpty) updates['path'] = _dbPathCtrl.text.trim();
      } else {
        if (_dbHostCtrl.text.isNotEmpty) updates['host'] = _dbHostCtrl.text.trim();
        if (_dbPortCtrl.text.isNotEmpty) updates['port'] = int.tryParse(_dbPortCtrl.text) ?? 5432;
        if (_dbNameCtrl.text.isNotEmpty) updates['name'] = _dbNameCtrl.text.trim();
        if (_dbUserCtrl.text.isNotEmpty) updates['user'] = _dbUserCtrl.text.trim();
        if (_dbPassCtrl.text.isNotEmpty) updates['password'] = _dbPassCtrl.text;
      }
      await ApiService.updateDeptDbConfig(userId: _uid, password: _pw, dept: _selectedDept, updates: updates);
      setState(() { _successMsg = 'DB config saved for $_selectedDept'; });
    } catch (e) {
      setState(() { _error = e.toString(); });
    } finally {
      setState(() { _dbSaving = false; });
    }
  }

  Future<void> _testDbConnection() async {
    setState(() { _dbTesting = true; _dbTestResult = null; _error = null; });
    try {
      final result = await ApiService.testDeptDbConnection(userId: _uid, password: _pw, dept: _selectedDept);
      setState(() { _dbTestResult = result; });
    } catch (e) {
      setState(() { _dbTestResult = {'ok': false, 'error': e.toString()}; });
    } finally {
      setState(() { _dbTesting = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: RapidColors.primary,
      appBar: AppBar(
        backgroundColor: RapidColors.surface,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: RapidColors.textPrimary),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: const Text('Department Settings', style: TextStyle(color: RapidColors.textPrimary, fontSize: 18, fontWeight: FontWeight.w600)),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: _DeptSelector(
              depts: _allDepts,
              selected: _selectedDept,
              onChanged: (d) {
                setState(() { _selectedDept = d; });
                _loadDeptConfig();
              },
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: RapidColors.accent))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_error != null) _ErrorBanner(_error!),
                  if (_successMsg != null) _SuccessBanner(_successMsg!),
                  const SizedBox(height: 8),
                  _buildRagSection(),
                  const SizedBox(height: 32),
                  _buildDbSection(),
                ],
              ),
            ),
    );
  }

  // ── RAG Config Section ────────────────────────────────────────────────────

  Widget _buildRagSection() {
    return _SectionCard(
      title: '${_selectedDept.toUpperCase()} — RAG Pipeline Configuration',
      icon: Icons.psychology,
      children: [
        // Stats row
        if (_loadingStats)
          const Padding(
            padding: EdgeInsets.only(bottom: 12),
            child: LinearProgressIndicator(color: RapidColors.accent),
          )
        else if (_ragStats != null)
          _RagStatsRow(stats: _ragStats!),
        const SizedBox(height: 16),

        // Embedding model
        _DropdownField(
          label: 'Embedding Model',
          value: _embeddingModel,
          items: _embeddingModels,
          onChanged: (v) => setState(() => _embeddingModel = v!),
        ),
        const SizedBox(height: 16),

        // Numeric fields row 1
        Row(children: [
          Expanded(child: _NumericField(label: 'Chunk Size', controller: _chunkSizeCtrl, hint: '512')),
          const SizedBox(width: 16),
          Expanded(child: _NumericField(label: 'Chunk Overlap', controller: _chunkOverlapCtrl, hint: '64')),
          const SizedBox(width: 16),
          Expanded(child: _NumericField(label: 'Top-K', controller: _topKCtrl, hint: '10')),
        ]),
        const SizedBox(height: 16),

        // Numeric fields row 2
        Row(children: [
          Expanded(child: _NumericField(label: 'Similarity Threshold', controller: _simThreshCtrl, hint: '0.25', isDecimal: true)),
          const SizedBox(width: 16),
          Expanded(child: _NumericField(label: 'RRF Alpha (vector)', controller: _rrfAlphaCtrl, hint: '0.6', isDecimal: true)),
          const SizedBox(width: 16),
          Expanded(child: _NumericField(label: 'BM25 Alpha', controller: _bm25AlphaCtrl, hint: '0.4', isDecimal: true)),
        ]),
        const SizedBox(height: 16),

        // HyDE toggle
        Row(
          children: [
            const Text('HyDE Query Rewriting', style: TextStyle(color: RapidColors.textSecondary, fontSize: 14)),
            const Spacer(),
            Switch(
              value: _hydeEnabled,
              activeColor: RapidColors.accent,
              onChanged: (v) => setState(() => _hydeEnabled = v),
            ),
          ],
        ),
        const SizedBox(height: 20),

        // Save button
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: RapidColors.accent,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            onPressed: _ragSaving ? null : _saveRagConfig,
            icon: _ragSaving
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                : const Icon(Icons.save),
            label: const Text('Save RAG Config'),
          ),
        ),
      ],
    );
  }

  // ── DB Config Section ─────────────────────────────────────────────────────

  Widget _buildDbSection() {
    return _SectionCard(
      title: '${_selectedDept.toUpperCase()} — Database Connection',
      icon: Icons.storage,
      children: [
        // Enable toggle
        Row(
          children: [
            const Text('Enable Department DB', style: TextStyle(color: RapidColors.textSecondary, fontSize: 14)),
            const Spacer(),
            Switch(
              value: _dbEnabled,
              activeColor: RapidColors.accent,
              onChanged: (v) => setState(() => _dbEnabled = v),
            ),
          ],
        ),
        const SizedBox(height: 16),

        // DB type selector
        _DropdownField(
          label: 'Database Type',
          value: _dbType,
          items: const ['sqlite', 'postgresql', 'mysql'],
          onChanged: _dbEnabled ? (v) => setState(() { _dbType = v!; }) : null,
        ),
        const SizedBox(height: 16),

        // SQLite path
        if (_dbType == 'sqlite') ...[
          _InputField(
            label: 'SQLite File Path',
            controller: _dbPathCtrl,
            hint: 'data/db/${_selectedDept}.db',
            enabled: _dbEnabled,
          ),
        ] else ...[
          Row(children: [
            Expanded(child: _InputField(label: 'Host', controller: _dbHostCtrl, hint: 'localhost', enabled: _dbEnabled)),
            const SizedBox(width: 12),
            SizedBox(width: 100, child: _InputField(label: 'Port', controller: _dbPortCtrl, hint: '5432', enabled: _dbEnabled, isNumeric: true)),
          ]),
          const SizedBox(height: 12),
          _InputField(label: 'Database Name', controller: _dbNameCtrl, hint: 'my_database', enabled: _dbEnabled),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: _InputField(label: 'User', controller: _dbUserCtrl, hint: 'admin', enabled: _dbEnabled)),
            const SizedBox(width: 12),
            Expanded(child: _PasswordField(label: 'Password', controller: _dbPassCtrl, enabled: _dbEnabled, visible: _dbPassVisible, onToggle: () => setState(() => _dbPassVisible = !_dbPassVisible))),
          ]),
        ],
        const SizedBox(height: 20),

        // Test result
        if (_dbTestResult != null) _DbTestResultTile(_dbTestResult!),
        const SizedBox(height: 12),

        // Buttons row
        Row(children: [
          Expanded(
            child: OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: RapidColors.accent,
                side: const BorderSide(color: RapidColors.accent),
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              onPressed: (_dbTesting || !_dbEnabled) ? null : _testDbConnection,
              icon: _dbTesting
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(color: RapidColors.accent, strokeWidth: 2))
                  : const Icon(Icons.cable),
              label: const Text('Test Connection'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: RapidColors.accent,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              onPressed: _dbSaving ? null : _saveDbConfig,
              icon: _dbSaving
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                  : const Icon(Icons.save),
              label: const Text('Save DB Config'),
            ),
          ),
        ]),
      ],
    );
  }
}


// ── Reusable widgets ──────────────────────────────────────────────────────────

class _DeptSelector extends StatelessWidget {
  final List<String> depts;
  final String selected;
  final ValueChanged<String> onChanged;

  const _DeptSelector({required this.depts, required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      decoration: BoxDecoration(
        color: RapidColors.surface,
        border: Border.all(color: RapidColors.divider),
        borderRadius: BorderRadius.circular(8),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: selected,
          dropdownColor: RapidColors.surface,
          style: const TextStyle(color: RapidColors.textPrimary, fontSize: 14),
          items: depts.map((d) => DropdownMenuItem(value: d, child: Text(d.toUpperCase()))).toList(),
          onChanged: (v) { if (v != null) onChanged(v); },
        ),
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final List<Widget> children;

  const _SectionCard({required this.title, required this.icon, required this.children});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: RapidColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(20),
            child: Row(children: [
              Icon(icon, color: RapidColors.accent, size: 20),
              const SizedBox(width: 10),
              Text(title, style: const TextStyle(color: RapidColors.textPrimary, fontSize: 15, fontWeight: FontWeight.w600)),
            ]),
          ),
          const Divider(color: RapidColors.divider, height: 1),
          Padding(
            padding: const EdgeInsets.all(20),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
          ),
        ],
      ),
    );
  }
}

class _RagStatsRow extends StatelessWidget {
  final Map<String, dynamic> stats;
  const _RagStatsRow({required this.stats});

  @override
  Widget build(BuildContext context) {
    final docCount = stats['doc_count'] ?? 0;
    final sources  = (stats['sources'] as List<dynamic>?) ?? [];
    final dim      = stats['index_dim'] ?? '–';
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: RapidColors.primary,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: RapidColors.divider),
      ),
      child: Row(children: [
        _StatChip(label: 'Chunks', value: '$docCount'),
        const SizedBox(width: 16),
        _StatChip(label: 'Sources', value: '${sources.length}'),
        const SizedBox(width: 16),
        _StatChip(label: 'Dim', value: '$dim'),
        if (sources.isNotEmpty) ...[
          const SizedBox(width: 16),
          Expanded(
            child: Text(sources.take(3).join(', ') + (sources.length > 3 ? '…' : ''),
              style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ]),
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label, value;
  const _StatChip({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
      Text(value, style: const TextStyle(color: RapidColors.accent, fontSize: 16, fontWeight: FontWeight.bold)),
    ]);
  }
}

class _DropdownField extends StatelessWidget {
  final String label;
  final String value;
  final List<String> items;
  final ValueChanged<String?>? onChanged;

  const _DropdownField({required this.label, required this.value, required this.items, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
      const SizedBox(height: 6),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: RapidColors.primary,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: RapidColors.divider),
        ),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<String>(
            isExpanded: true,
            value: value,
            dropdownColor: RapidColors.surface,
            style: const TextStyle(color: RapidColors.textPrimary, fontSize: 14),
            items: items.map((i) => DropdownMenuItem(value: i, child: Text(i))).toList(),
            onChanged: onChanged,
          ),
        ),
      ),
    ]);
  }
}

class _NumericField extends StatelessWidget {
  final String label, hint;
  final TextEditingController controller;
  final bool isDecimal;

  const _NumericField({required this.label, required this.controller, required this.hint, this.isDecimal = false});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
      const SizedBox(height: 6),
      TextField(
        controller: controller,
        keyboardType: isDecimal ? const TextInputType.numberWithOptions(decimal: true) : TextInputType.number,
        style: const TextStyle(color: RapidColors.textPrimary, fontSize: 14),
        decoration: InputDecoration(
          hintText: hint,
          hintStyle: const TextStyle(color: RapidColors.textSecondary),
          filled: true,
          fillColor: RapidColors.primary,
          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent)),
        ),
      ),
    ]);
  }
}

class _InputField extends StatelessWidget {
  final String label, hint;
  final TextEditingController controller;
  final bool enabled;
  final bool isNumeric;

  const _InputField({required this.label, required this.controller, required this.hint, required this.enabled, this.isNumeric = false});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
      const SizedBox(height: 6),
      TextField(
        controller: controller,
        enabled: enabled,
        keyboardType: isNumeric ? TextInputType.number : TextInputType.text,
        style: const TextStyle(color: RapidColors.textPrimary, fontSize: 14),
        decoration: InputDecoration(
          hintText: hint,
          hintStyle: const TextStyle(color: RapidColors.textSecondary),
          filled: true,
          fillColor: enabled ? RapidColors.primary : RapidColors.surface,
          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent)),
          disabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: RapidColors.divider.withOpacity(0.5))),
        ),
      ),
    ]);
  }
}

class _PasswordField extends StatelessWidget {
  final String label;
  final TextEditingController controller;
  final bool enabled, visible;
  final VoidCallback onToggle;

  const _PasswordField({required this.label, required this.controller, required this.enabled, required this.visible, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
      const SizedBox(height: 6),
      TextField(
        controller: controller,
        enabled: enabled,
        obscureText: !visible,
        style: const TextStyle(color: RapidColors.textPrimary, fontSize: 14),
        decoration: InputDecoration(
          hintText: '••••••••',
          hintStyle: const TextStyle(color: RapidColors.textSecondary),
          filled: true,
          fillColor: enabled ? RapidColors.primary : RapidColors.surface,
          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
          suffixIcon: IconButton(icon: Icon(visible ? Icons.visibility_off : Icons.visibility, color: RapidColors.textSecondary, size: 18), onPressed: onToggle),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent)),
          disabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: RapidColors.divider.withOpacity(0.5))),
        ),
      ),
    ]);
  }
}

class _DbTestResultTile extends StatelessWidget {
  final Map<String, dynamic> result;
  const _DbTestResultTile(this.result);

  @override
  Widget build(BuildContext context) {
    final ok  = result['ok'] == true;
    final msg = ok ? 'Connection successful (${result['type'] ?? ''})' : (result['error'] ?? 'Unknown error');
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: ok ? RapidColors.success.withOpacity(0.08) : RapidColors.error.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: ok ? RapidColors.success.withOpacity(0.5) : RapidColors.error.withOpacity(0.5)),
      ),
      child: Row(children: [
        Icon(ok ? Icons.check_circle : Icons.error, color: ok ? RapidColors.success : RapidColors.error, size: 16),
        const SizedBox(width: 8),
        Expanded(child: Text(msg, style: TextStyle(color: ok ? RapidColors.success : RapidColors.error, fontSize: 13))),
      ]),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  const _ErrorBanner(this.message);

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: RapidColors.error.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: RapidColors.error.withOpacity(0.5)),
      ),
      child: Row(children: [
        Icon(Icons.error_outline, color: RapidColors.error, size: 16),
        const SizedBox(width: 8),
        Expanded(child: Text(message, style: TextStyle(color: RapidColors.error, fontSize: 13))),
      ]),
    );
  }
}

class _SuccessBanner extends StatelessWidget {
  final String message;
  const _SuccessBanner(this.message);

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: RapidColors.success.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: RapidColors.success.withOpacity(0.5)),
      ),
      child: Row(children: [
        Icon(Icons.check_circle_outline, color: RapidColors.success, size: 16),
        const SizedBox(width: 8),
        Expanded(child: Text(message, style: TextStyle(color: RapidColors.success, fontSize: 13))),
      ]),
    );
  }
}
