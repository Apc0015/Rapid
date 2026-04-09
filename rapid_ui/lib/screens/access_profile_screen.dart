import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../theme.dart';

/// Access profile screen — shows the current user's own project/dept access
/// and lets them toggle DB mode on/off.
class AccessProfileScreen extends StatefulWidget {
  const AccessProfileScreen({super.key});

  @override
  State<AccessProfileScreen> createState() => _AccessProfileScreenState();
}

class _AccessProfileScreenState extends State<AccessProfileScreen> {
  Map<String, dynamic>? _profile;
  bool _loading = true;
  String? _error;
  bool _togglingDb = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final auth = context.read<AuthProvider>();
    setState(() { _loading = true; _error = null; });
    try {
      final data = await ApiService.myAccess(
        userId:   auth.userId!,
        password: auth.password!,
      );
      setState(() { _profile = data; _loading = false; });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _loading = false; });
    }
  }

  Future<void> _toggleDbMode(bool enabled) async {
    final auth = context.read<AuthProvider>();
    setState(() => _togglingDb = true);
    try {
      await ApiService.toggleDbMode(
        userId:   auth.userId!,
        password: auth.password!,
        enabled:  enabled,
      );
      auth.setDbMode(enabled);
      // Update local profile display
      if (_profile != null) {
        setState(() { _profile!['db_mode_enabled'] = enabled; });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(e.toString().replaceFirst('Exception: ', '')),
          backgroundColor: RapidColors.error,
        ));
      }
    } finally {
      if (mounted) setState(() => _togglingDb = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    return Scaffold(
      backgroundColor: RapidColors.primary,
      appBar: AppBar(
        backgroundColor: RapidColors.surface,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: RapidColors.textSecondary),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('My Access Profile',
            style: TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w700)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: RapidColors.textSecondary, size: 20),
            onPressed: _load,
            tooltip: 'Refresh',
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: RapidColors.accent))
          : _error != null
              ? Center(child: _ErrorView(message: _error!, onRetry: _load))
              : _buildBody(auth),
    );
  }

  Widget _buildBody(AuthProvider auth) {
    final p = _profile!;
    final depts    = (p['permitted_departments'] as List?)?.cast<String>() ?? [];
    final projects = (p['project_access'] as Map<String, dynamic>?) ?? {};
    final dbMode   = p['db_mode_enabled'] as bool? ?? false;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Profile card
          _Card(
            child: Row(
              children: [
                CircleAvatar(
                  radius: 28,
                  backgroundColor: RapidColors.accent.withOpacity(0.15),
                  child: Text(
                    (p['name'] as String? ?? auth.userId ?? '?')[0].toUpperCase(),
                    style: const TextStyle(color: RapidColors.accent, fontSize: 22, fontWeight: FontWeight.w700),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(p['name'] as String? ?? auth.userId ?? '',
                          style: const TextStyle(color: RapidColors.textPrimary, fontSize: 17, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 3),
                      Text(p['email'] as String? ?? '',
                          style: const TextStyle(color: RapidColors.textSecondary, fontSize: 13)),
                      const SizedBox(height: 3),
                      Row(children: [
                        _roleBadge(p['role'] as String? ?? ''),
                        const SizedBox(width: 8),
                        Text('ID: ${p['rapid_user_id'] as String? ?? '-'}',
                            style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
                      ]),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Department access
          _sectionTitle('Department Access'),
          const SizedBox(height: 10),
          _Card(
            child: depts.isEmpty
                ? const Text('No departments assigned.', style: TextStyle(color: RapidColors.textSecondary))
                : Wrap(
                    spacing: 8, runSpacing: 8,
                    children: depts.map((d) => _deptChip(d)).toList(),
                  ),
          ),
          const SizedBox(height: 16),

          // DB mode toggle
          _sectionTitle('Database Mode'),
          const SizedBox(height: 10),
          _Card(
            child: Row(
              children: [
                const Icon(Icons.storage_rounded, color: RapidColors.accent, size: 20),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Direct DB Queries', style: TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w600, fontSize: 14)),
                      SizedBox(height: 2),
                      Text('When enabled, RAPID searches your company databases in addition to documents.',
                          style: TextStyle(color: RapidColors.textSecondary, fontSize: 12, height: 1.4)),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                _togglingDb
                    ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2, color: RapidColors.accent))
                    : Switch(
                        value: dbMode,
                        onChanged: _toggleDbMode,
                        activeColor: RapidColors.accent,
                      ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Project access per dept
          if (projects.isNotEmpty) ...[
            _sectionTitle('Project Access'),
            const SizedBox(height: 10),
            ...projects.entries.map((e) => _ProjectCard(dept: e.key, projects: (e.value as List?)?.cast<String>() ?? [])),
          ],
        ],
      ),
    );
  }

  Widget _sectionTitle(String text) => Text(
    text,
    style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5),
  );

  Widget _roleBadge(String role) {
    final color = role == 'admin' ? RapidColors.error
        : role == 'manager' ? RapidColors.accent
        : RapidColors.textSecondary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Text(role, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }

  Widget _deptChip(String dept) {
    const deptEmoji = {
      'hr': '👥', 'finance': '💰', 'legal': '⚖️', 'sales': '🛒',
      'marketing': '📈', 'ops': '⚙️', 'it': '💻',
      'procurement': '📦', 'rd': '🔬', 'customer_success': '🎯',
    };
    final emoji = deptEmoji[dept] ?? '🏢';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: RapidColors.accent.withOpacity(0.08),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: RapidColors.accent.withOpacity(0.25)),
      ),
      child: Text('$emoji $dept', style: const TextStyle(color: RapidColors.accent, fontSize: 12, fontWeight: FontWeight.w500)),
    );
  }
}

class _ProjectCard extends StatelessWidget {
  final String dept;
  final List<String> projects;
  const _ProjectCard({required this.dept, required this.projects});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: RapidColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: RapidColors.surfaceAlt,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(10)),
            ),
            child: Row(children: [
              const Icon(Icons.folder_outlined, color: RapidColors.textSecondary, size: 16),
              const SizedBox(width: 8),
              Text(dept.toUpperCase(),
                  style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.5)),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: projects.isEmpty
                ? const Text('No project restrictions.', style: TextStyle(color: RapidColors.textSecondary, fontSize: 12))
                : Wrap(
                    spacing: 6, runSpacing: 6,
                    children: projects.map((p) => Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: RapidColors.surfaceAlt,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: RapidColors.divider),
                      ),
                      child: Text(p, style: const TextStyle(color: RapidColors.textPrimary, fontSize: 12)),
                    )).toList(),
                  ),
          ),
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  final Widget child;
  const _Card({required this.child});

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: RapidColors.surface,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: RapidColors.divider),
      boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 6)],
    ),
    child: child,
  );
}

class _ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorView({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(24),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.error_outline, color: RapidColors.error, size: 40),
        const SizedBox(height: 12),
        Text(message,
            style: const TextStyle(color: RapidColors.textSecondary, fontSize: 13),
            textAlign: TextAlign.center),
        const SizedBox(height: 16),
        TextButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh, size: 16),
          label: const Text('Retry'),
          style: TextButton.styleFrom(foregroundColor: RapidColors.accent),
        ),
      ],
    ),
  );
}
