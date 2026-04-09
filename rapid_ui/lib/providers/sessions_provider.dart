import 'package:flutter/material.dart';
import '../models/chat_session.dart';
import '../services/api_service.dart';
import 'chat_provider.dart';

class SessionsProvider extends ChangeNotifier {
  List<ChatSession> _sessions = [];
  String? _activeSessionId;
  bool _loading = false;

  List<ChatSession> get sessions => List.unmodifiable(_sessions);
  String? get activeSessionId => _activeSessionId;
  bool get loading => _loading;

  // ── Grouped views ─────────────────────────────────────────────────────────

  List<ChatSession> get todaySessions {
    final today = DateTime.now();
    return _sessions.where((s) {
      final d = s.updatedAt.toLocal();
      return d.year == today.year && d.month == today.month && d.day == today.day;
    }).toList();
  }

  List<ChatSession> get yesterdaySessions {
    final yesterday = DateTime.now().subtract(const Duration(days: 1));
    return _sessions.where((s) {
      final d = s.updatedAt.toLocal();
      return d.year == yesterday.year && d.month == yesterday.month && d.day == yesterday.day;
    }).toList();
  }

  List<ChatSession> get last7DaysSessions {
    final now = DateTime.now();
    final cutoff = now.subtract(const Duration(days: 7));
    final yesterday = now.subtract(const Duration(days: 1));
    return _sessions.where((s) {
      final d = s.updatedAt.toLocal();
      final isToday = d.year == now.year && d.month == now.month && d.day == now.day;
      final isYesterday = d.year == yesterday.year && d.month == yesterday.month && d.day == yesterday.day;
      return !isToday && !isYesterday && d.isAfter(cutoff);
    }).toList();
  }

  List<ChatSession> get olderSessions {
    final cutoff = DateTime.now().subtract(const Duration(days: 7));
    return _sessions.where((s) => s.updatedAt.toLocal().isBefore(cutoff)).toList();
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  Future<void> loadSessions() async {
    _loading = true;
    notifyListeners();
    try {
      _sessions = await ApiService.listSessions();
    } catch (_) {
      // Non-fatal: sidebar just stays empty
      _sessions = [];
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<ChatSession> createSession({String title = 'New Chat'}) async {
    final session = await ApiService.createSession(title: title);
    _sessions.insert(0, session);
    _activeSessionId = session.id;
    notifyListeners();
    return session;
  }

  Future<void> deleteSession(String sessionId) async {
    await ApiService.deleteSession(sessionId: sessionId);
    _sessions.removeWhere((s) => s.id == sessionId);
    if (_activeSessionId == sessionId) _activeSessionId = null;
    notifyListeners();
  }

  Future<void> loadMessages(String sessionId, ChatProvider chatProvider) async {
    try {
      final messages = await ApiService.getSessionMessages(sessionId: sessionId);
      chatProvider.loadFromHistory(messages, sessionId);
      _activeSessionId = sessionId;
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  void setActive(String? sessionId) {
    _activeSessionId = sessionId;
    notifyListeners();
  }

  /// Called after a new chat is started — refreshes session title in the sidebar.
  void refreshSession(ChatSession updated) {
    final idx = _sessions.indexWhere((s) => s.id == updated.id);
    if (idx >= 0) {
      _sessions[idx] = updated;
    } else {
      _sessions.insert(0, updated);
    }
    notifyListeners();
  }

  void clear() {
    _sessions = [];
    _activeSessionId = null;
    notifyListeners();
  }
}
