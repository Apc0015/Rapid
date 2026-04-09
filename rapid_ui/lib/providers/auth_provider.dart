import 'package:flutter/material.dart';
import '../services/api_service.dart';

class AuthProvider extends ChangeNotifier {
  String? _userId;
  String? _password;    // kept only for changePassword (needs current password)
  String? _role;
  String? _name;
  String? _email;
  String? _rapidUserId;
  bool    _dbModeEnabled = false;
  String? _errorMessage;
  bool    _loading = false;

  // ── JWT state ────────────────────────────────────────────────────────────────
  String? _accessToken;
  String? _refreshToken;

  String? get userId       => _userId;
  String? get password     => _password;   // current plain password (for change-password)
  String? get role         => _role;
  String? get name         => _name;
  String? get email        => _email;
  String? get rapidUserId  => _rapidUserId;
  bool    get dbModeEnabled => _dbModeEnabled;
  String? get errorMessage => _errorMessage;
  bool    get isLoggedIn   => _userId != null && _accessToken != null;
  bool    get loading      => _loading;
  bool    get isAdmin        => _role == 'admin';
  bool    get isManager      => _role == 'admin' || _role == 'manager';
  bool    get isDeptHead     => isAdmin || isManager || _role == 'dept_head';
  bool    get isDivisionHead => isAdmin || _role == 'division_head' || _role == 'c_suite' || _role == 'ceo';
  bool    get isExecutive    => _role == 'ceo' || _role == 'board_member' || isAdmin;
  bool    get isBoardMember  => _role == 'board_member';

  Future<bool> login(String username, String password) async {
    _loading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final profile = await ApiService.login(
        userId: username.trim(),
        password: password.trim(),
      );

      _userId         = profile['user_id']  as String?  ?? username.trim();
      _password       = password.trim();   // kept for changePassword only
      _role           = profile['role']     as String?  ?? 'employee';
      _name           = profile['name']     as String?  ?? username;
      _email          = profile['email']    as String?  ?? '';
      _rapidUserId    = profile['rapid_user_id'] as String? ?? '';
      _dbModeEnabled  = profile['db_mode_enabled'] as bool? ?? false;

      // Store JWT tokens and inject them into ApiService
      _accessToken  = profile['access_token']  as String?;
      _refreshToken = profile['refresh_token'] as String?;
      if (_accessToken != null && _refreshToken != null) {
        ApiService.setTokens(_accessToken!, _refreshToken!);
      }

      _loading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _errorMessage = e.toString().replaceFirst('Exception: ', '');
      _loading = false;
      notifyListeners();
      return false;
    }
  }

  /// Call after a successful password change — clears stale credentials.
  void updatePassword(String newPassword) {
    _password = newPassword;
    notifyListeners();
  }

  void setDbMode(bool enabled) {
    _dbModeEnabled = enabled;
    notifyListeners();
  }

  Future<void> logout() async {
    // Tell the backend to revoke the refresh token (best-effort)
    await ApiService.logout();
    _clearState();
  }

  Future<void> logoutAll() async {
    await ApiService.logoutAll();
    _clearState();
  }

  void _clearState() {
    _userId         = null;
    _password       = null;
    _role           = null;
    _name           = null;
    _email          = null;
    _rapidUserId    = null;
    _dbModeEnabled  = false;
    _errorMessage   = null;
    _accessToken    = null;
    _refreshToken   = null;
    ApiService.clearTokens();
    notifyListeners();
  }
}
