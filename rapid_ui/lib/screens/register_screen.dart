import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../theme.dart';

/// Self-registration screen — any employee can submit an access request.
/// No authentication needed; the request goes through dept-head + admin review.
class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _nameCtrl          = TextEditingController();
  final _emailCtrl         = TextEditingController();
  final _empIdCtrl         = TextEditingController();
  final _passwordCtrl      = TextEditingController();
  final _confirmCtrl       = TextEditingController();
  final _justificationCtrl = TextEditingController();

  bool _passVisible    = false;
  bool _confirmVisible = false;
  bool _submitting     = false;
  String? _error;
  String? _successMsg;

  List<String> _allDepts = [];
  final List<String> _selectedDepts = [];

  @override
  void initState() {
    super.initState();
    _loadDepts();
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _empIdCtrl.dispose();
    _passwordCtrl.dispose();
    _confirmCtrl.dispose();
    _justificationCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadDepts() async {
    try {
      final meta = await ApiService.userMeta();
      if (mounted) setState(() => _allDepts = List<String>.from(meta['departments'] ?? []));
    } catch (_) {}
  }

  Future<void> _submit() async {
    final name   = _nameCtrl.text.trim();
    final email  = _emailCtrl.text.trim();
    final empId  = _empIdCtrl.text.trim();
    final pass   = _passwordCtrl.text.trim();
    final confirm = _confirmCtrl.text.trim();
    final just   = _justificationCtrl.text.trim();

    if (name.isEmpty || email.isEmpty || empId.isEmpty || pass.isEmpty || just.isEmpty) {
      setState(() => _error = 'Please fill in all required fields.');
      return;
    }
    if (pass.length < 8) {
      setState(() => _error = 'Password must be at least 8 characters.');
      return;
    }
    if (pass != confirm) {
      setState(() => _error = 'Passwords do not match.');
      return;
    }
    if (_selectedDepts.isEmpty) {
      setState(() => _error = 'Select at least one department you need access to.');
      return;
    }
    if (!email.contains('@')) {
      setState(() => _error = 'Enter a valid organisation email address.');
      return;
    }

    setState(() { _submitting = true; _error = null; });

    try {
      final res = await ApiService.register(
        employeeName:   name,
        orgEmail:       email,
        password:       pass,
        employeeId:     empId,
        requestedDepts: _selectedDepts,
        justification:  just,
      );
      setState(() {
        _submitting  = false;
        _successMsg  = res['message'] as String? ??
            'Request submitted (${res['request_id']}). You will receive your login once approved.';
      });
    } catch (e) {
      setState(() {
        _submitting = false;
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: RapidColors.primary,
      appBar: AppBar(
        backgroundColor: RapidColors.surface,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: RapidColors.textSecondary),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('Request RAPID Access',
            style: TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w700)),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: _successMsg != null ? _buildSuccess() : _buildForm(),
        ),
      ),
    );
  }

  Widget _buildSuccess() {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.check_circle_outline, color: RapidColors.success, size: 64),
          const SizedBox(height: 20),
          const Text('Request Submitted!',
              style: TextStyle(color: RapidColors.textPrimary, fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          Text(_successMsg!,
              style: const TextStyle(color: RapidColors.textSecondary, fontSize: 14, height: 1.6),
              textAlign: TextAlign.center),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () => Navigator.pop(context),
              style: ElevatedButton.styleFrom(
                backgroundColor: RapidColors.accent,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              ),
              child: const Text('Back to Login'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildForm() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Banner
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: RapidColors.accent.withOpacity(0.06),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: RapidColors.accent.withOpacity(0.2)),
            ),
            child: const Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.info_outline, color: RapidColors.accent, size: 18),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Fill in your details to request access. Your request will be reviewed by your '
                    'department head, then the RAPID admin. You\'ll receive your login credentials once approved.',
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 12, height: 1.5),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          _label('Full Name *'),
          _field(_nameCtrl, 'e.g. John Smith'),
          const SizedBox(height: 14),

          _label('Organisation Email *'),
          _field(_emailCtrl, 'e.g. john.smith@company.com', type: TextInputType.emailAddress),
          const SizedBox(height: 14),

          _label('Employee ID *'),
          _field(_empIdCtrl, 'e.g. EMP-2024-042'),
          const SizedBox(height: 14),

          _label('Password *'),
          _passField(_passwordCtrl, 'At least 8 characters', _passVisible,
              () => setState(() => _passVisible = !_passVisible)),
          const SizedBox(height: 14),

          _label('Confirm Password *'),
          _passField(_confirmCtrl, 'Re-enter password', _confirmVisible,
              () => setState(() => _confirmVisible = !_confirmVisible)),
          const SizedBox(height: 20),

          _label('Departments you need access to *'),
          const SizedBox(height: 8),
          _allDepts.isEmpty
              ? const Text('Loading departments…',
                  style: TextStyle(color: RapidColors.textSecondary, fontSize: 12))
              : Wrap(
                  spacing: 8, runSpacing: 8,
                  children: _allDepts.map((d) {
                    final sel = _selectedDepts.contains(d);
                    return FilterChip(
                      label: Text(d),
                      selected: sel,
                      selectedColor: RapidColors.accent.withOpacity(0.15),
                      backgroundColor: RapidColors.surfaceAlt,
                      labelStyle: TextStyle(
                        color: sel ? RapidColors.accent : RapidColors.textSecondary,
                        fontSize: 12,
                      ),
                      side: BorderSide(color: sel ? RapidColors.accent : RapidColors.divider),
                      onSelected: (v) => setState(() => v ? _selectedDepts.add(d) : _selectedDepts.remove(d)),
                    );
                  }).toList(),
                ),
          const SizedBox(height: 20),

          _label('Justification / Reason for access *'),
          const SizedBox(height: 6),
          TextField(
            controller: _justificationCtrl,
            maxLines: 4,
            style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
            decoration: InputDecoration(
              hintText: 'Explain why you need access and what you will use RAPID for…',
              hintStyle: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
              filled: true, fillColor: RapidColors.surfaceAlt,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent)),
              isDense: true, contentPadding: const EdgeInsets.all(12),
            ),
          ),
          const SizedBox(height: 20),

          if (_error != null)
            Container(
              margin: const EdgeInsets.only(bottom: 12),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: RapidColors.error.withOpacity(0.08),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: RapidColors.error.withOpacity(0.3)),
              ),
              child: Row(children: [
                const Icon(Icons.error_outline, color: RapidColors.error, size: 16),
                const SizedBox(width: 8),
                Expanded(child: Text(_error!, style: const TextStyle(color: RapidColors.error, fontSize: 13))),
              ]),
            ),

          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              icon: _submitting
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.send_outlined, size: 18),
              label: Text(_submitting ? 'Submitting…' : 'Submit Access Request'),
              onPressed: _submitting ? null : _submit,
              style: ElevatedButton.styleFrom(
                backgroundColor: RapidColors.accent,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              ),
            ),
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  Widget _label(String text) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Text(text, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
  );

  Widget _field(TextEditingController ctrl, String hint, {TextInputType type = TextInputType.text}) =>
    TextField(
      controller: ctrl,
      keyboardType: type,
      style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: const TextStyle(color: RapidColors.textSecondary),
        filled: true, fillColor: RapidColors.surfaceAlt,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent)),
        isDense: true, contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      ),
    );

  Widget _passField(TextEditingController ctrl, String hint, bool visible, VoidCallback toggle) =>
    TextField(
      controller: ctrl,
      obscureText: !visible,
      style: const TextStyle(color: RapidColors.textPrimary, fontSize: 13),
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: const TextStyle(color: RapidColors.textSecondary),
        filled: true, fillColor: RapidColors.surfaceAlt,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.divider)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: RapidColors.accent)),
        isDense: true, contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        suffixIcon: IconButton(
          icon: Icon(visible ? Icons.visibility_off : Icons.visibility, size: 16, color: RapidColors.textSecondary),
          onPressed: toggle,
        ),
      ),
    );
}
