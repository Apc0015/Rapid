import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../models/query_response.dart';
import '../services/api_service.dart';

class ChatProvider extends ChangeNotifier {
  final List<ChatMessage> _messages = [];
  bool _loading = false;
  String? _errorMessage;
  String? _currentSessionId;

  // Pending file attachment
  String? pendingFileName;
  Uint8List? pendingFileBytes;

  List<ChatMessage> get messages => List.unmodifiable(_messages);
  bool get loading => _loading;
  String? get errorMessage => _errorMessage;
  bool get hasAttachment => pendingFileName != null;
  String? get currentSessionId => _currentSessionId;

  void setSession(String? sessionId) {
    _currentSessionId = sessionId;
    // Don't notify here — caller will clear messages themselves
  }

  // Build history list for backend (last 10 turns)
  List<HistoryMessage> _buildHistory() {
    final history = <HistoryMessage>[];
    for (final msg in _messages.reversed.take(10).toList().reversed) {
      history.add(HistoryMessage(
        role: msg.isUser ? 'user' : 'assistant',
        content: msg.text,
      ));
    }
    return history;
  }

  void attachFile(String name, Uint8List bytes) {
    pendingFileName = name;
    pendingFileBytes = bytes;
    notifyListeners();
  }

  void clearAttachment() {
    pendingFileName = null;
    pendingFileBytes = null;
    notifyListeners();
  }

  /// Populate messages from saved session history (called when user taps a session).
  void loadFromHistory(List<Map<String, dynamic>> messages, String sessionId) {
    _messages.clear();
    _currentSessionId = sessionId;
    for (final m in messages) {
      _messages.add(ChatMessage(
        text:   m['content'] as String,
        isUser: m['role'] == 'user',
      ));
    }
    _loading = false;
    _errorMessage = null;
    notifyListeners();
  }

  Future<void> sendQuery({
    required String queryText,
    bool useWeb = false,
    String? sessionId,
    // legacy params kept for call-site compatibility — no longer used
    String userId = '',
    String password = '',
  }) async {
    // Capture both before clearing
    final attachName  = pendingFileName;
    final attachBytes = pendingFileBytes;

    // Use provided sessionId or the current one
    final effectiveSessionId = sessionId ?? _currentSessionId;
    if (effectiveSessionId != null) {
      _currentSessionId = effectiveSessionId;
    }

    // Add user message immediately (show attachment name if any)
    _messages.add(ChatMessage(
      text: queryText,
      isUser: true,
      attachedFileName: attachName,
    ));
    _loading = true;
    _errorMessage = null;
    clearAttachment();
    notifyListeners();

    try {
      final response = await ApiService.query(
        queryText: queryText,
        history:   _buildHistory(),
        attachedFileBytes: attachBytes,
        attachedFileName:  attachName,
        useWeb:    useWeb,
        sessionId: _currentSessionId,
      );
      _messages.add(ChatMessage(
        text: response.answer,
        isUser: false,
        response: response,
      ));
    } catch (e) {
      _errorMessage = e.toString().replaceFirst('Exception: ', '');
      _messages.add(ChatMessage(
        text: 'Error: $_errorMessage',
        isUser: false,
      ));
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  void clearHistory() {
    _messages.clear();
    _currentSessionId = null;
    _errorMessage = null;
    clearAttachment();
    notifyListeners();
  }
}
