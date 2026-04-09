import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../models/audit_entry.dart';
import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../theme.dart';
import '../widgets/dept_badge.dart';
import '../widgets/confidence_bar.dart';

class AuditScreen extends StatefulWidget {
  const AuditScreen({super.key});

  @override
  State<AuditScreen> createState() => _AuditScreenState();
}

class _AuditScreenState extends State<AuditScreen> {
  List<AuditEntry> _entries = [];
  bool _loading = true;
  String? _error;
  final _userFilter  = TextEditingController();
  String _eventFilter = '';
  int _limit = 50;

  final List<String> _eventTypes = ['', 'query', 'auth_failure', 'governance_action', 'gap_flagged'];

  @override
  void initState() {
    super.initState();
    _fetchAudit();
  }

  @override
  void dispose() {
    _userFilter.dispose();
    super.dispose();
  }

  Future<void> _fetchAudit() async {
    final auth = context.read<AuthProvider>();
    setState(() { _loading = true; _error = null; });
    try {
      final entries = await ApiService.auditLog(
        userId:    auth.userId!,
        password:  auth.password!,
        filterUid: _userFilter.text.trim().isEmpty ? null : _userFilter.text.trim(),
        eventType: _eventFilter.isEmpty ? null : _eventFilter,
        limit:     _limit,
      );
      setState(() { _entries = entries; _loading = false; });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _loading = false; });
    }
  }

  String _formatTs(String raw) {
    try {
      final dt = DateTime.parse(raw).toLocal();
      return DateFormat('dd MMM HH:mm').format(dt);
    } catch (_) {
      return raw;
    }
  }

  Color _confidenceColor(double? c) {
    if (c == null) return RapidColors.textSecondary;
    if (c >= 0.65) return RapidColors.success;
    if (c >= 0.40) return RapidColors.warning;
    return RapidColors.error;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: RapidColors.primary,
      appBar: AppBar(
        title: const Text('Audit Log'),
        backgroundColor: RapidColors.surface,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: RapidColors.textSecondary),
          onPressed: () => Navigator.pop(context),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: RapidColors.textSecondary),
            onPressed: _fetchAudit,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: Column(
        children: [
          // Filters
          Container(
            color: RapidColors.surface,
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _userFilter,
                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                    decoration: const InputDecoration(
                      hintText: 'Filter by user…',
                      prefixIcon: Icon(Icons.person_search_outlined, size: 18, color: RapidColors.textSecondary),
                      isDense: true,
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    ),
                    onSubmitted: (_) => _fetchAudit(),
                  ),
                ),
                const SizedBox(width: 12),
                DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: _eventFilter,
                    dropdownColor: RapidColors.surface,
                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                    items: _eventTypes.map((t) => DropdownMenuItem(
                      value: t,
                      child: Text(t.isEmpty ? 'All events' : t, style: const TextStyle(color: RapidColors.textPrimary)),
                    )).toList(),
                    onChanged: (v) {
                      setState(() => _eventFilter = v ?? '');
                      _fetchAudit();
                    },
                  ),
                ),
                const SizedBox(width: 12),
                DropdownButtonHideUnderline(
                  child: DropdownButton<int>(
                    value: _limit,
                    dropdownColor: RapidColors.surface,
                    style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
                    items: [25, 50, 100, 200].map((n) => DropdownMenuItem(
                      value: n,
                      child: Text('$n rows', style: const TextStyle(color: RapidColors.textPrimary)),
                    )).toList(),
                    onChanged: (v) {
                      setState(() => _limit = v ?? 50);
                      _fetchAudit();
                    },
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _fetchAudit,
                  style: ElevatedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10)),
                  child: const Text('Search'),
                ),
              ],
            ),
          ),

          const Divider(height: 1),

          // Content
          Expanded(
            child: _loading
              ? const Center(child: CircularProgressIndicator(color: RapidColors.accent))
              : _error != null
                ? Center(child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline, color: RapidColors.error, size: 40),
                      const SizedBox(height: 12),
                      Text(_error!, style: const TextStyle(color: RapidColors.error)),
                    ],
                  ))
                : _entries.isEmpty
                  ? const Center(child: Text('No audit entries found', style: TextStyle(color: RapidColors.textSecondary)))
                  : ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: _entries.length,
                      itemBuilder: (ctx, i) => _AuditCard(
                        entry: _entries[i],
                        formatTs: _formatTs,
                        confidenceColor: _confidenceColor,
                      ),
                    ),
          ),
        ],
      ),
    );
  }
}

class _AuditCard extends StatelessWidget {
  final AuditEntry entry;
  final String Function(String) formatTs;
  final Color Function(double?) confidenceColor;

  const _AuditCard({required this.entry, required this.formatTs, required this.confidenceColor});

  @override
  Widget build(BuildContext context) {
    final isAuthFail = entry.eventType == 'auth_failure' || entry.intentClass == 'AUTH_FAIL';

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: isAuthFail ? RapidColors.error.withOpacity(0.4) : RapidColors.divider,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: isAuthFail ? RapidColors.error.withOpacity(0.15) : RapidColors.accent.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  entry.eventType ?? entry.intentClass,
                  style: TextStyle(
                    color: isAuthFail ? RapidColors.error : RapidColors.accent,
                    fontSize: 11, fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(entry.userId, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
              const Spacer(),
              Text(formatTs(entry.timestamp), style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            entry.rawQuery.isNotEmpty ? entry.rawQuery : '(no query)',
            style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          if (entry.deptsActivated.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              children: entry.deptsActivated.map((d) => DeptBadge(dept: d)).toList(),
            ),
          ],
          if (entry.compositeConfidence != null) ...[
            const SizedBox(height: 8),
            ConfidenceBar(confidence: entry.compositeConfidence!),
          ],
          if (entry.actionTaken.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text('Action: ${entry.actionTaken}',
              style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
          ],
        ],
      ),
    );
  }
}
