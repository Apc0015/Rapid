import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../theme.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Entry — tabs depend on role
//   Admin:     [Admin Review] [Dept Review] [All Requests] [All Users]
//   Dept head: [My Dept Requests] [All Users]
//   Manager:   [All Users] (view only)
// ─────────────────────────────────────────────────────────────────────────────

class UserManagementScreen extends StatefulWidget {
  const UserManagementScreen({super.key});

  @override
  State<UserManagementScreen> createState() => _UserManagementScreenState();
}

class _UserManagementScreenState extends State<UserManagementScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  late List<Tab>     _tabList;
  late List<Widget>  _tabViews;

  @override
  void initState() {
    super.initState();
    final auth = context.read<AuthProvider>();

    if (auth.isAdmin) {
      _tabList  = const [
        Tab(text: 'Admin Review'),
        Tab(text: 'Division Review'),
        Tab(text: 'Dept Review'),
        Tab(text: 'All Requests'),
        Tab(text: 'All Users'),
      ];
      _tabViews = const [
        _AdminReviewTab(),
        _DivisionReviewTab(),
        _DeptHeadTab(),
        _AllRequestsTab(),
        _AllUsersTab(),
      ];
    } else if (auth.isDivisionHead) {
      _tabList  = const [Tab(text: 'Division Review'), Tab(text: 'All Users')];
      _tabViews = const [_DivisionReviewTab(), _AllUsersTab()];
    } else if (auth.isDeptHead) {
      _tabList  = const [Tab(text: 'My Requests'), Tab(text: 'All Users')];
      _tabViews = const [_DeptHeadTab(), _AllUsersTab()];
    } else {
      _tabList  = const [Tab(text: 'All Users')];
      _tabViews = const [_AllUsersTab()];
    }

    _tabs = TabController(length: _tabList.length, vsync: this);
  }

  @override
  void dispose() { _tabs.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: RapidColors.primary,
      appBar: AppBar(
        title: const Text('User Management'),
        backgroundColor: RapidColors.surface,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: RapidColors.textSecondary),
          onPressed: () => Navigator.pop(context),
        ),
        bottom: TabBar(
          controller: _tabs,
          labelColor: RapidColors.accent,
          unselectedLabelColor: RapidColors.textSecondary,
          indicatorColor: RapidColors.accent,
          tabs: _tabList,
        ),
      ),
      body: TabBarView(controller: _tabs, children: _tabViews),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Admin Review tab — requests at admin_review stage
// ─────────────────────────────────────────────────────────────────────────────
class _AdminReviewTab extends StatefulWidget {
  const _AdminReviewTab();
  @override State<_AdminReviewTab> createState() => _AdminReviewTabState();
}

class _AdminReviewTabState extends State<_AdminReviewTab> {
  List<dynamic> _requests = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    final auth = context.read<AuthProvider>();
    setState(() { _loading = true; _error = null; });
    try {
      final reqs = await ApiService.adminRequests(userId: auth.userId!, password: auth.password!);
      setState(() { _requests = reqs; _loading = false; });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator(color: RapidColors.accent));
    if (_error != null) return _errorView(_error!, _load);

    return RefreshIndicator(
      onRefresh: _load, color: RapidColors.accent,
      child: _requests.isEmpty
          ? const _EmptyState(message: 'No requests awaiting admin review.')
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _requests.length,
              itemBuilder: (_, i) => _AdminRequestCard(
                req: _requests[i] as Map<String, dynamic>,
                onRefresh: _load,
              ),
            ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Admin request card — approve / reject
// ─────────────────────────────────────────────────────────────────────────────
class _AdminRequestCard extends StatefulWidget {
  final Map<String, dynamic> req;
  final VoidCallback onRefresh;
  const _AdminRequestCard({required this.req, required this.onRefresh});
  @override State<_AdminRequestCard> createState() => _AdminRequestCardState();
}

class _AdminRequestCardState extends State<_AdminRequestCard> {
  bool _expanded = false;
  bool _acting   = false;
  final _notesCtrl = TextEditingController();

  @override
  void dispose() { _notesCtrl.dispose(); super.dispose(); }

  Future<void> _approve() async {
    final auth = context.read<AuthProvider>();
    setState(() => _acting = true);
    try {
      final res = await ApiService.adminApproveRequest(
        adminId:  auth.userId!,
        password: auth.password!,
        reqId:    widget.req['request_id'],
        notes:    _notesCtrl.text.trim(),
      );
      if (!mounted) return;
      _showResult(
        title: 'Account Created',
        color: RapidColors.success,
        body: '${res['message']}\n\nLogin key: ${res['login_key'] ?? '-'}',
      );
      widget.onRefresh();
    } catch (e) {
      if (!mounted) return;
      _showResult(title: 'Error', color: RapidColors.error,
          body: e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _reject() async {
    final auth = context.read<AuthProvider>();
    setState(() => _acting = true);
    try {
      await ApiService.adminRejectRequest(
        adminId:  auth.userId!,
        password: auth.password!,
        reqId:    widget.req['request_id'],
        notes:    _notesCtrl.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Request rejected.'), backgroundColor: RapidColors.error),
      );
      widget.onRefresh();
    } catch (e) {
      if (!mounted) return;
      _showResult(title: 'Error', color: RapidColors.error,
          body: e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  void _showResult({required String title, required Color color, required String body}) {
    showDialog(context: context, builder: (_) => AlertDialog(
      backgroundColor: RapidColors.surface,
      title: Text(title, style: TextStyle(color: color, fontWeight: FontWeight.w700)),
      content: SelectableText(body, style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13)),
      actions: [TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Close', style: TextStyle(color: RapidColors.accent)),
      )],
    ));
  }

  @override
  Widget build(BuildContext context) {
    final r = widget.req;
    return _RequestCard(
      req: r,
      expanded: _expanded,
      onToggle: () => setState(() => _expanded = !_expanded),
      actions: _expanded ? _buildActions(r) : null,
    );
  }

  Widget _buildActions(Map<String, dynamic> r) {
    return Column(
      children: [
        // Dept approvals summary
        if (r['dept_approvals'] != null) ...[
          const SizedBox(height: 12),
          _DeptApprovalsView(approvals: r['dept_approvals'] as Map<String, dynamic>),
        ],
        const SizedBox(height: 12),
        TextField(
          controller: _notesCtrl,
          maxLines: 2,
          style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
          decoration: _inputDec('Admin notes (optional)'),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: _rejectBtn(_acting ? null : _reject)),
          const SizedBox(width: 12),
          Expanded(child: _approveBtn(_acting ? null : _approve, 'Final Approve')),
        ]),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Dept Head tab — requests pending dept-head review
// ─────────────────────────────────────────────────────────────────────────────
class _DeptHeadTab extends StatefulWidget {
  const _DeptHeadTab();
  @override State<_DeptHeadTab> createState() => _DeptHeadTabState();
}

class _DeptHeadTabState extends State<_DeptHeadTab> {
  List<dynamic> _requests = [];
  List<String>  _myDepts  = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    final auth = context.read<AuthProvider>();
    setState(() { _loading = true; _error = null; });
    try {
      final data = await ApiService.deptRequests(userId: auth.userId!, password: auth.password!);
      setState(() {
        _requests = data['requests'] as List? ?? [];
        _myDepts  = (data['my_depts'] as List?)?.cast<String>() ?? [];
        _loading  = false;
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator(color: RapidColors.accent));
    if (_error != null) return _errorView(_error!, _load);

    return RefreshIndicator(
      onRefresh: _load, color: RapidColors.accent,
      child: _requests.isEmpty
          ? _EmptyState(message: _myDepts.isEmpty
              ? 'You are not assigned as head of any department.'
              : 'No requests pending for: ${_myDepts.join(", ")}')
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _requests.length,
              itemBuilder: (_, i) => _DeptRequestCard(
                req:     _requests[i] as Map<String, dynamic>,
                myDepts: _myDepts,
                onRefresh: _load,
              ),
            ),
    );
  }
}

class _DeptRequestCard extends StatefulWidget {
  final Map<String, dynamic> req;
  final List<String> myDepts;
  final VoidCallback onRefresh;
  const _DeptRequestCard({required this.req, required this.myDepts, required this.onRefresh});
  @override State<_DeptRequestCard> createState() => _DeptRequestCardState();
}

class _DeptRequestCardState extends State<_DeptRequestCard> {
  bool _expanded = false;
  bool _acting   = false;
  String? _selectedDept;
  final _notesCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    // Pre-select the dept from the request if we are head of it
    final reqDepts = (widget.req['requested_depts'] as List?)?.cast<String>() ?? [];
    _selectedDept = widget.myDepts.firstWhere(
      (d) => reqDepts.contains(d),
      orElse: () => widget.myDepts.isNotEmpty ? widget.myDepts.first : '',
    );
  }

  @override
  void dispose() { _notesCtrl.dispose(); super.dispose(); }

  Future<void> _approve() async {
    if (_selectedDept == null || _selectedDept!.isEmpty) return;
    final auth = context.read<AuthProvider>();
    setState(() => _acting = true);
    try {
      await ApiService.deptApproveRequest(
        userId:   auth.userId!,
        password: auth.password!,
        reqId:    widget.req['request_id'],
        dept:     _selectedDept!,
        notes:    _notesCtrl.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Department approved — forwarded to admin.'),
        backgroundColor: RapidColors.success,
      ));
      widget.onRefresh();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(e.toString().replaceFirst('Exception: ', '')),
        backgroundColor: RapidColors.error,
      ));
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _reject() async {
    if (_selectedDept == null || _selectedDept!.isEmpty) return;
    final auth = context.read<AuthProvider>();
    setState(() => _acting = true);
    try {
      await ApiService.deptRejectRequest(
        userId:   auth.userId!,
        password: auth.password!,
        reqId:    widget.req['request_id'],
        dept:     _selectedDept!,
        notes:    _notesCtrl.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Request rejected.'), backgroundColor: RapidColors.error));
      widget.onRefresh();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(e.toString().replaceFirst('Exception: ', '')),
        backgroundColor: RapidColors.error,
      ));
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _RequestCard(
      req: widget.req,
      expanded: _expanded,
      onToggle: () => setState(() => _expanded = !_expanded),
      actions: _expanded ? _buildActions() : null,
    );
  }

  Widget _buildActions() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (widget.myDepts.length > 1) ...[
          const SizedBox(height: 12),
          const Text('Reviewing for dept:',
              style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          DropdownButtonFormField<String>(
            value: _selectedDept,
            dropdownColor: RapidColors.surface,
            style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
            decoration: _inputDec('Select department'),
            items: widget.myDepts.map((d) => DropdownMenuItem(value: d, child: Text(d))).toList(),
            onChanged: (v) => setState(() => _selectedDept = v),
          ),
        ],
        const SizedBox(height: 12),
        TextField(
          controller: _notesCtrl, maxLines: 2,
          style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
          decoration: _inputDec('Notes (optional)'),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: _rejectBtn(_acting ? null : _reject)),
          const SizedBox(width: 12),
          Expanded(child: _approveBtn(_acting ? null : _approve, 'Approve for ${_selectedDept ?? "dept"}')),
        ]),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Division Review tab — for c_suite / division_head roles
// ─────────────────────────────────────────────────────────────────────────────
class _DivisionReviewTab extends StatefulWidget {
  const _DivisionReviewTab();
  @override State<_DivisionReviewTab> createState() => _DivisionReviewTabState();
}

class _DivisionReviewTabState extends State<_DivisionReviewTab> {
  List<dynamic> _requests   = [];
  List<String>  _myDivisions = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    final auth = context.read<AuthProvider>();
    setState(() { _loading = true; _error = null; });
    try {
      final data = await ApiService.divisionRequests(userId: auth.userId!, password: auth.password!);
      setState(() {
        _requests    = data['requests'] as List? ?? [];
        _myDivisions = (data['my_divisions'] as List?)?.cast<String>() ?? [];
        _loading     = false;
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator(color: RapidColors.accent));
    if (_error != null) return _errorView(_error!, _load);

    return RefreshIndicator(
      onRefresh: _load, color: RapidColors.accent,
      child: _requests.isEmpty
          ? _EmptyState(message: _myDivisions.isEmpty
              ? 'You are not assigned as head of any division.'
              : 'No requests pending for divisions: ${_myDivisions.join(", ")}')
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _requests.length,
              itemBuilder: (_, i) => _DivisionRequestCard(
                req:         _requests[i] as Map<String, dynamic>,
                myDivisions: _myDivisions,
                onRefresh:   _load,
              ),
            ),
    );
  }
}

class _DivisionRequestCard extends StatefulWidget {
  final Map<String, dynamic> req;
  final List<String> myDivisions;
  final VoidCallback onRefresh;
  const _DivisionRequestCard({required this.req, required this.myDivisions, required this.onRefresh});
  @override State<_DivisionRequestCard> createState() => _DivisionRequestCardState();
}

class _DivisionRequestCardState extends State<_DivisionRequestCard> {
  bool _expanded  = false;
  bool _acting    = false;
  String? _selectedDivision;
  final _notesCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _selectedDivision = widget.myDivisions.isNotEmpty ? widget.myDivisions.first : null;
  }

  @override
  void dispose() { _notesCtrl.dispose(); super.dispose(); }

  Future<void> _approve() async {
    if (_selectedDivision == null) return;
    final auth = context.read<AuthProvider>();
    setState(() => _acting = true);
    try {
      await ApiService.divisionApproveRequest(
        userId:   auth.userId!,
        password: auth.password!,
        reqId:    widget.req['request_id'],
        division: _selectedDivision!,
        notes:    _notesCtrl.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Division approved — forwarded to admin review.'),
        backgroundColor: RapidColors.success,
      ));
      widget.onRefresh();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(e.toString().replaceFirst('Exception: ', '')),
        backgroundColor: RapidColors.error,
      ));
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _reject() async {
    if (_selectedDivision == null) return;
    final auth = context.read<AuthProvider>();
    setState(() => _acting = true);
    try {
      await ApiService.divisionRejectRequest(
        userId:   auth.userId!,
        password: auth.password!,
        reqId:    widget.req['request_id'],
        division: _selectedDivision!,
        notes:    _notesCtrl.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Request rejected.'), backgroundColor: RapidColors.error));
      widget.onRefresh();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(e.toString().replaceFirst('Exception: ', '')),
        backgroundColor: RapidColors.error,
      ));
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _RequestCard(
      req: widget.req,
      expanded: _expanded,
      onToggle: () => setState(() => _expanded = !_expanded),
      actions: _expanded ? _buildActions() : null,
    );
  }

  Widget _buildActions() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (widget.req['dept_approvals'] != null) ...[
          const SizedBox(height: 12),
          _DeptApprovalsView(approvals: widget.req['dept_approvals'] as Map<String, dynamic>),
        ],
        if (widget.myDivisions.length > 1) ...[
          const SizedBox(height: 12),
          const Text('Reviewing for division:',
            style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          DropdownButtonFormField<String>(
            value: _selectedDivision,
            dropdownColor: RapidColors.surface,
            style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
            decoration: _inputDec('Select division'),
            items: widget.myDivisions.map((d) => DropdownMenuItem(value: d, child: Text(d))).toList(),
            onChanged: (v) => setState(() => _selectedDivision = v),
          ),
        ],
        const SizedBox(height: 12),
        TextField(
          controller: _notesCtrl, maxLines: 2,
          style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
          decoration: _inputDec('Notes (optional)'),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: _rejectBtn(_acting ? null : _reject)),
          const SizedBox(width: 12),
          Expanded(child: _approveBtn(_acting ? null : _approve, 'Approve (${_selectedDivision ?? "div"})')),
        ]),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// All Requests tab (admin only)
// ─────────────────────────────────────────────────────────────────────────────
class _AllRequestsTab extends StatefulWidget {
  const _AllRequestsTab();
  @override State<_AllRequestsTab> createState() => _AllRequestsTabState();
}

class _AllRequestsTabState extends State<_AllRequestsTab> {
  List<dynamic> _requests = [];
  bool _loading = true;
  String? _stageFilter;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    final auth = context.read<AuthProvider>();
    setState(() => _loading = true);
    try {
      final reqs = await ApiService.allRequests(
        userId: auth.userId!, password: auth.password!, stage: _stageFilter);
      setState(() { _requests = reqs; _loading = false; });
    } catch (_) { setState(() => _loading = false); }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Stage filter chips
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(
            children: [null, 'pending', 'dept_review', 'division_review', 'admin_review', 'approved', 'rejected']
                .map((s) => Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(s ?? 'All'),
                      selected: _stageFilter == s,
                      selectedColor: RapidColors.accent.withOpacity(0.2),
                      backgroundColor: RapidColors.surfaceAlt,
                      labelStyle: TextStyle(
                        color: _stageFilter == s ? RapidColors.accent : RapidColors.textSecondary,
                        fontSize: 12,
                      ),
                      side: BorderSide(color: _stageFilter == s ? RapidColors.accent : RapidColors.divider),
                      onSelected: (_) { _stageFilter = s; _load(); },
                    )))
                .toList(),
          ),
        ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator(color: RapidColors.accent))
              : RefreshIndicator(
                  onRefresh: _load, color: RapidColors.accent,
                  child: _requests.isEmpty
                      ? const _EmptyState(message: 'No requests found.')
                      : ListView.builder(
                          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                          itemCount: _requests.length,
                          itemBuilder: (_, i) => _RequestCard(
                            req: _requests[i] as Map<String, dynamic>,
                            expanded: false,
                            onToggle: () {},
                          ),
                        ),
                ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// All Users tab
// ─────────────────────────────────────────────────────────────────────────────
class _AllUsersTab extends StatefulWidget {
  const _AllUsersTab();
  @override State<_AllUsersTab> createState() => _AllUsersTabState();
}

class _AllUsersTabState extends State<_AllUsersTab> {
  List<dynamic> _users = [];
  bool _loading = true;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    final auth = context.read<AuthProvider>();
    setState(() => _loading = true);
    try {
      final users = await ApiService.listPortalUsers(userId: auth.userId!, password: auth.password!);
      setState(() { _users = users; _loading = false; });
    } catch (_) { setState(() => _loading = false); }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator(color: RapidColors.accent));
    return RefreshIndicator(
      onRefresh: _load, color: RapidColors.accent,
      child: _users.isEmpty
          ? const _EmptyState(message: 'No users yet.')
          : ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: _users.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (_, i) => _UserTile(user: _users[i] as Map<String, dynamic>),
            ),
    );
  }
}

class _UserTile extends StatelessWidget {
  final Map<String, dynamic> user;
  const _UserTile({required this.user});

  @override
  Widget build(BuildContext context) {
    final depts = (user['permitted_departments'] as List?)?.cast<String>() ?? [];
    final role  = user['role'] as String? ?? '';
    final Color roleColor = role == 'admin' ? RapidColors.error
        : role == 'manager' ? RapidColors.accent
        : RapidColors.textSecondary;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: RapidColors.divider),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.03), blurRadius: 4)],
      ),
      child: Row(children: [
        Container(
          width: 44, height: 44,
          decoration: BoxDecoration(color: RapidColors.accent.withOpacity(0.1), shape: BoxShape.circle),
          child: Center(child: Text(
            (user['name'] as String? ?? '?')[0].toUpperCase(),
            style: const TextStyle(color: RapidColors.accent, fontWeight: FontWeight.w700, fontSize: 18),
          )),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Text(user['name'] as String? ?? '',
                style: const TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w600, fontSize: 14)),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: roleColor.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: roleColor.withOpacity(0.3)),
                ),
                child: Text(role, style: TextStyle(color: roleColor, fontSize: 10, fontWeight: FontWeight.w600)),
              ),
            ]),
            const SizedBox(height: 2),
            Text('${user['rapid_user_id'] ?? '-'} • ${user['employee_id'] ?? '-'} • ${user['email'] ?? '-'}',
              style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 4, runSpacing: 4,
              children: depts.map((d) => Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: RapidColors.accent.withOpacity(0.08),
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: RapidColors.accent.withOpacity(0.2)),
                ),
                child: Text(d, style: const TextStyle(color: RapidColors.accent, fontSize: 10)),
              )).toList(),
            ),
          ]),
        ),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared — generic request card (collapsible)
// ─────────────────────────────────────────────────────────────────────────────
class _RequestCard extends StatelessWidget {
  final Map<String, dynamic> req;
  final bool expanded;
  final VoidCallback onToggle;
  final Widget? actions;

  const _RequestCard({
    required this.req,
    required this.expanded,
    required this.onToggle,
    this.actions,
  });

  @override
  Widget build(BuildContext context) {
    final status = req['stage'] as String? ?? req['status'] as String? ?? '-';
    final statusColor = status == 'approved' ? RapidColors.success
        : status == 'rejected' ? RapidColors.error
        : status == 'admin_review' ? RapidColors.accent
        : RapidColors.warning;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: RapidColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: statusColor.withOpacity(0.25)),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 6)],
      ),
      child: Column(children: [
        InkWell(
          onTap: onToggle,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(children: [
              Container(
                width: 38, height: 38,
                decoration: BoxDecoration(
                  color: RapidColors.accent.withOpacity(0.1), shape: BoxShape.circle),
                child: Center(child: Text(
                  (req['employee_name'] as String? ?? '?')[0].toUpperCase(),
                  style: const TextStyle(color: RapidColors.accent, fontWeight: FontWeight.w700, fontSize: 15),
                )),
              ),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(req['employee_name'] as String? ?? '',
                  style: const TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w600, fontSize: 14)),
                const SizedBox(height: 2),
                Text(
                  '${req['employee_id'] ?? '-'} • ${(req['requested_depts'] as List?)?.join(", ") ?? '-'}',
                  style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11),
                ),
                const SizedBox(height: 2),
                Text(_fmtDate(req['submitted_at'] as String?),
                  style: const TextStyle(color: RapidColors.textSecondary, fontSize: 10)),
              ])),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                decoration: BoxDecoration(
                  color: statusColor.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: statusColor.withOpacity(0.4)),
                ),
                child: Text(status.replaceAll('_', ' ').toUpperCase(),
                  style: TextStyle(color: statusColor, fontSize: 9, fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: 6),
              Icon(expanded ? Icons.expand_less : Icons.expand_more,
                color: RapidColors.textSecondary, size: 18),
            ]),
          ),
        ),
        if (expanded) ...[
          const Divider(height: 1, color: RapidColors.divider),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              _row('Email',       req['org_email'] as String? ?? req['employee_email'] as String? ?? '-'),
              _row('Employee ID', req['employee_id'] as String? ?? '-'),
              _row('Request ID',  req['request_id'] as String? ?? '-'),
              if ((req['requested_depts'] as List?)?.isNotEmpty == true)
                _row('Requested depts', (req['requested_depts'] as List).join(', ')),
              const SizedBox(height: 10),
              const Text('Justification',
                style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(color: RapidColors.surfaceAlt, borderRadius: BorderRadius.circular(8)),
                child: Text(req['justification'] as String? ?? '-',
                  style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13)),
              ),
              if (actions != null) actions!,
            ]),
          ),
        ],
      ]),
    );
  }

  Widget _row(String label, String value) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(width: 110,
        child: Text(label, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600))),
      Expanded(child: Text(value, style: const TextStyle(color: RapidColors.textPrimary, fontSize: 12))),
    ]),
  );

  static String _fmtDate(String? iso) {
    if (iso == null) return '-';
    try {
      final d = DateTime.parse(iso);
      return '${d.day}/${d.month}/${d.year}';
    } catch (_) { return iso; }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Dept approvals summary widget
// ─────────────────────────────────────────────────────────────────────────────
class _DeptApprovalsView extends StatelessWidget {
  final Map<String, dynamic> approvals;
  const _DeptApprovalsView({required this.approvals});

  @override
  Widget build(BuildContext context) {
    if (approvals.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Dept approvals:',
          style: TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
        const SizedBox(height: 6),
        Wrap(
          spacing: 8, runSpacing: 6,
          children: approvals.entries.map((e) {
            final status = (e.value as Map<String, dynamic>?)?['status'] as String? ?? '-';
            final color = status == 'approved' ? RapidColors.success
                : status == 'rejected' ? RapidColors.error : RapidColors.warning;
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: color.withOpacity(0.08),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: color.withOpacity(0.3)),
              ),
              child: Text('${e.key}: $status',
                style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600)),
            );
          }).toList(),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared helpers
// ─────────────────────────────────────────────────────────────────────────────

class _EmptyState extends StatelessWidget {
  final String message;
  const _EmptyState({required this.message});

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(40),
      child: Text(message, style: const TextStyle(color: RapidColors.textSecondary), textAlign: TextAlign.center),
    ),
  );
}

InputDecoration _inputDec(String label) => InputDecoration(
  labelText: label,
  labelStyle: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
  filled: true, fillColor: RapidColors.surfaceAlt,
  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
  enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
  focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent)),
  isDense: true, contentPadding: const EdgeInsets.all(12),
);

Widget _rejectBtn(VoidCallback? onTap) => OutlinedButton.icon(
  icon: const Icon(Icons.close, size: 15, color: RapidColors.error),
  label: const Text('Reject', style: TextStyle(color: RapidColors.error)),
  onPressed: onTap,
  style: OutlinedButton.styleFrom(
    side: const BorderSide(color: RapidColors.error),
    padding: const EdgeInsets.symmetric(vertical: 12),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
  ),
);

Widget _approveBtn(VoidCallback? onTap, String label) => ElevatedButton.icon(
  icon: const Icon(Icons.check, size: 15),
  label: Text(label, overflow: TextOverflow.ellipsis),
  onPressed: onTap,
  style: ElevatedButton.styleFrom(
    backgroundColor: RapidColors.success,
    foregroundColor: Colors.white,
    padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
  ),
);

Widget _errorView(String msg, VoidCallback retry) => Center(
  child: Padding(
    padding: const EdgeInsets.all(24),
    child: Column(mainAxisSize: MainAxisSize.min, children: [
      const Icon(Icons.error_outline, color: RapidColors.error, size: 36),
      const SizedBox(height: 10),
      Text(msg, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 13), textAlign: TextAlign.center),
      const SizedBox(height: 14),
      TextButton.icon(
        onPressed: retry,
        icon: const Icon(Icons.refresh, size: 16),
        label: const Text('Retry'),
        style: TextButton.styleFrom(foregroundColor: RapidColors.accent),
      ),
    ]),
  ),
);
