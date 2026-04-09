import 'dart:async';
import 'package:flutter/material.dart';
import '../models/cloud_models.dart';
import '../services/api_service.dart';

class CloudProvider extends ChangeNotifier {
  CloudStatus? onedriveStatus;
  CloudStatus? gmailStatus;

  List<CloudFile> onedriveFiles = [];
  List<GmailLabel> gmailLabels = [];
  List<GmailMessage> gmailMessages = [];
  String? selectedGmailLabelId;

  bool loadingOnedrive = false;
  bool loadingGmail    = false;
  bool importing       = false;
  String? importResult;
  String? importError;

  // ── Status checks ─────────────────────────────────────────────────────────

  Future<void> checkStatus() async {
    try {
      onedriveStatus = await ApiService.onedriveStatus();
    } catch (_) {
      onedriveStatus = const CloudStatus(connected: false);
    }
    try {
      gmailStatus = await ApiService.gmailStatus();
    } catch (_) {
      gmailStatus = const CloudStatus(connected: false);
    }
    notifyListeners();
  }

  // ── OneDrive ──────────────────────────────────────────────────────────────

  /// Returns the auth URL — caller opens it via url_launcher.
  Future<String> onedriveAuthUrl() => ApiService.onedriveConnectUrl();

  /// Poll backend every 2s until connected (max 120s). Returns true on success.
  Future<bool> waitForOnedriveConnection() async {
    const maxAttempts = 60;
    for (int i = 0; i < maxAttempts; i++) {
      await Future.delayed(const Duration(seconds: 2));
      try {
        final s = await ApiService.onedriveStatus();
        if (s.connected) {
          onedriveStatus = s;
          notifyListeners();
          return true;
        }
      } catch (_) {}
    }
    return false;
  }

  Future<void> loadOnedriveFiles({String path = '/'}) async {
    loadingOnedrive = true;
    notifyListeners();
    try {
      onedriveFiles = await ApiService.onedriveFiles(folderPath: path);
    } finally {
      loadingOnedrive = false;
      notifyListeners();
    }
  }

  Future<void> importOnedriveFile(String itemId, String deptTag) async {
    importing    = true;
    importResult = null;
    importError  = null;
    notifyListeners();
    try {
      final r = await ApiService.onedriveImport(itemId: itemId, deptTag: deptTag);
      importResult = 'Imported ${r['file']} — ${r['chunks']} chunks created';
    } catch (e) {
      importError = e.toString().replaceFirst('Exception: ', '');
    } finally {
      importing = false;
      notifyListeners();
    }
  }

  Future<void> disconnectOnedrive() async {
    await ApiService.onedriveDisconnect();
    onedriveStatus = const CloudStatus(connected: false);
    onedriveFiles  = [];
    notifyListeners();
  }

  // ── Gmail ─────────────────────────────────────────────────────────────────

  Future<String> gmailAuthUrl() => ApiService.gmailConnectUrl();

  Future<bool> waitForGmailConnection() async {
    const maxAttempts = 60;
    for (int i = 0; i < maxAttempts; i++) {
      await Future.delayed(const Duration(seconds: 2));
      try {
        final s = await ApiService.gmailStatus();
        if (s.connected) {
          gmailStatus = s;
          notifyListeners();
          return true;
        }
      } catch (_) {}
    }
    return false;
  }

  Future<void> loadGmailLabels() async {
    loadingGmail = true;
    notifyListeners();
    try {
      gmailLabels = await ApiService.gmailLabels();
    } finally {
      loadingGmail = false;
      notifyListeners();
    }
  }

  Future<void> loadGmailMessages(String labelId) async {
    selectedGmailLabelId = labelId;
    loadingGmail = true;
    notifyListeners();
    try {
      gmailMessages = await ApiService.gmailMessages(labelId: labelId);
    } finally {
      loadingGmail = false;
      notifyListeners();
    }
  }

  Future<void> importGmailMessage(String messageId, String deptTag) async {
    importing    = true;
    importResult = null;
    importError  = null;
    notifyListeners();
    try {
      final r = await ApiService.gmailImportMessage(messageId: messageId, deptTag: deptTag);
      importResult = 'Imported email — ${r['chunks']} chunks created';
    } catch (e) {
      importError = e.toString().replaceFirst('Exception: ', '');
    } finally {
      importing = false;
      notifyListeners();
    }
  }

  Future<void> disconnectGmail() async {
    await ApiService.gmailDisconnect();
    gmailStatus   = const CloudStatus(connected: false);
    gmailLabels   = [];
    gmailMessages = [];
    notifyListeners();
  }
}
