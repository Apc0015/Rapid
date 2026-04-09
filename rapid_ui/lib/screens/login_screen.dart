import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../providers/auth_provider.dart';
import '../theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _userCtrl  = TextEditingController();
  final _tokenCtrl = TextEditingController();
  final _formKey   = GlobalKey<FormState>();
  bool _obscure    = true;

  @override
  void dispose() {
    _userCtrl.dispose();
    _tokenCtrl.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    final auth = context.read<AuthProvider>();
    final ok = await auth.login(_userCtrl.text.trim(), _tokenCtrl.text.trim());
    if (ok && mounted) {
      Navigator.pushReplacementNamed(context, '/chat');
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final isWide = MediaQuery.of(context).size.width > 700;

    return Scaffold(
      backgroundColor: RapidColors.primary,
      body: Center(
        child: SingleChildScrollView(
          child: Container(
            width: isWide ? 420 : double.infinity,
            margin: const EdgeInsets.all(24),
            padding: const EdgeInsets.all(40),
            decoration: BoxDecoration(
              color: RapidColors.surface,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: RapidColors.divider),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.08),
                  blurRadius: 24,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Logo
                  Container(
                    width: 64, height: 64,
                    decoration: BoxDecoration(
                      color: RapidColors.accent.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: RapidColors.accent.withOpacity(0.5)),
                    ),
                    child: const Center(
                      child: Text('R', style: TextStyle(
                        color: RapidColors.accent,
                        fontSize: 32, fontWeight: FontWeight.w800,
                      )),
                    ),
                  ).animate().scale(duration: 400.ms, curve: Curves.elasticOut),
                  const SizedBox(height: 20),
                  const Text('RAPID', style: TextStyle(
                    color: RapidColors.textPrimary, fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: 3,
                  )).animate().fadeIn(delay: 100.ms),
                  const SizedBox(height: 4),
                  const Text('RAG Application for Private Instant Deployment',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: RapidColors.textSecondary, fontSize: 12),
                  ).animate().fadeIn(delay: 150.ms),
                  const SizedBox(height: 36),

                  // Username
                  TextFormField(
                    controller: _userCtrl,
                    style: const TextStyle(color: RapidColors.textPrimary),
                    decoration: const InputDecoration(
                      labelText: 'Username',
                      prefixIcon: Icon(Icons.person_outline, color: RapidColors.textSecondary, size: 20),
                    ),
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'Enter your username' : null,
                    onFieldSubmitted: (_) => _login(),
                  ).animate().fadeIn(delay: 200.ms).slideY(begin: 0.1),
                  const SizedBox(height: 14),

                  // Password
                  TextFormField(
                    controller: _tokenCtrl,
                    obscureText: _obscure,
                    style: const TextStyle(color: RapidColors.textPrimary),
                    decoration: InputDecoration(
                      labelText: 'Password',
                      prefixIcon: const Icon(Icons.lock_outline, color: RapidColors.textSecondary, size: 20),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                          color: RapidColors.textSecondary, size: 20),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'Enter your password' : null,
                    onFieldSubmitted: (_) => _login(),
                  ).animate().fadeIn(delay: 250.ms).slideY(begin: 0.1),
                  const SizedBox(height: 24),

                  // Error
                  if (auth.errorMessage != null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: RapidColors.error.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: RapidColors.error.withOpacity(0.4)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, color: RapidColors.error, size: 16),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(auth.errorMessage!, style: const TextStyle(color: RapidColors.error, fontSize: 13)),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],

                  // Login button
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: auth.loading ? null : _login,
                      child: auth.loading
                        ? const SizedBox(width: 20, height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Text('Sign In'),
                    ),
                  ).animate().fadeIn(delay: 300.ms),
                  const SizedBox(height: 20),

                  // Register link
                  TextButton(
                    onPressed: () => Navigator.pushNamed(context, '/register'),
                    child: const Text(
                      'New employee? Request access →',
                      style: TextStyle(color: RapidColors.textSecondary, fontSize: 13),
                    ),
                  ).animate().fadeIn(delay: 350.ms),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
