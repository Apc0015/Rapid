import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import '../models/query_response.dart';
import '../models/audit_entry.dart';
import '../models/chat_session.dart';
import '../models/cloud_models.dart';
export '../models/query_response.dart' show HistoryMessage;
export '../models/chat_session.dart';
export '../models/cloud_models.dart';

class ApiService {
  static const String baseUrl = 'http://localhost:8000';

  // ── Token storage (set by AuthProvider after login / refresh) ───────────────
  static String? _accessToken;
  static String? _refreshToken;

  static void setTokens(String access, String refresh) {
    _accessToken = access;
    _refreshToken = refresh;
  }

  static void clearTokens() {
    _accessToken = null;
    _refreshToken = null;
  }

  static bool get hasToken => _accessToken != null;

  // ── Internal helpers ────────────────────────────────────────────────────────

  static Map<String, String> _bearerHeaders() => {
    'Content-Type': 'application/json',
    if (_accessToken != null) 'Authorization': 'Bearer $_accessToken',
  };

  static Map<String, String> _bearerHeadersNoJson() => {
    if (_accessToken != null) 'Authorization': 'Bearer $_accessToken',
  };

  /// Attempt to refresh access token using stored refresh token.
  /// Returns true on success (also updates _accessToken).
  static Future<bool> _tryRefresh() async {
    if (_refreshToken == null) return false;
    try {
      final res = await http.post(
        Uri.parse('$baseUrl/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': _refreshToken}),
      );
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        _accessToken = data['access_token'] as String;
        return true;
      }
    } catch (_) {}
    return false;
  }

  /// GET with auto-refresh on 401.
  static Future<http.Response> _authGet(Uri uri) async {
    var res = await http.get(uri, headers: _bearerHeaders());
    if (res.statusCode == 401 && _refreshToken != null) {
      if (await _tryRefresh()) {
        res = await http.get(uri, headers: _bearerHeaders());
      }
    }
    return res;
  }

  /// POST with auto-refresh on 401.
  static Future<http.Response> _authPost(Uri uri, {Object? body}) async {
    var res = await http.post(uri, headers: _bearerHeaders(), body: body);
    if (res.statusCode == 401 && _refreshToken != null) {
      if (await _tryRefresh()) {
        res = await http.post(uri, headers: _bearerHeaders(), body: body);
      }
    }
    return res;
  }

  /// PUT with auto-refresh on 401.
  static Future<http.Response> _authPut(Uri uri, {Object? body}) async {
    var res = await http.put(uri, headers: _bearerHeaders(), body: body);
    if (res.statusCode == 401 && _refreshToken != null) {
      if (await _tryRefresh()) {
        res = await http.put(uri, headers: _bearerHeaders(), body: body);
      }
    }
    return res;
  }

  /// DELETE with auto-refresh on 401.
  static Future<http.Response> _authDelete(Uri uri) async {
    var res = await http.delete(uri, headers: _bearerHeaders());
    if (res.statusCode == 401 && _refreshToken != null) {
      if (await _tryRefresh()) {
        res = await http.delete(uri, headers: _bearerHeaders());
      }
    }
    return res;
  }

  // ── Health check ────────────────────────────────────────────────────────────
  static Future<Map<String, dynamic>> health() async {
    final res = await http.get(Uri.parse('$baseUrl/health'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception('Health check failed: ${res.statusCode}');
  }

  // ── Auth ────────────────────────────────────────────────────────────────────

  /// Login with login_key + password. Returns full profile map including tokens.
  static Future<Map<String, dynamic>> login({
    required String userId,
    required String password,
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'user_id': userId, 'password': password}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    final detail = _detail(res);
    throw Exception(detail);
  }

  /// Self-registration — any employee can apply.
  static Future<Map<String, dynamic>> register({
    required String employeeName,
    required String orgEmail,
    required String password,
    required String employeeId,
    required List<String> requestedDepts,
    required String justification,
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'employee_name':    employeeName,
        'org_email':        orgEmail,
        'password':         password,
        'employee_id':      employeeId,
        'requested_depts':  requestedDepts,
        'justification':    justification,
      }),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  /// Logout (revoke current device's refresh token).
  static Future<void> logout() async {
    if (_refreshToken != null) {
      try {
        await _authPost(
          Uri.parse('$baseUrl/auth/logout'),
          body: jsonEncode({'refresh_token': _refreshToken}),
        );
      } catch (_) {}
    }
    clearTokens();
  }

  /// Logout all devices.
  static Future<void> logoutAll() async {
    try {
      await _authPost(Uri.parse('$baseUrl/auth/logout-all'));
    } catch (_) {}
    clearTokens();
  }

  // ── Query ───────────────────────────────────────────────────────────────────
  static Future<QueryResponse> query({
    // userId / password kept for call-site compatibility but Bearer token is used
    String userId = '',
    String password = '',
    required String queryText,
    List<HistoryMessage> history = const [],
    Uint8List? attachedFileBytes,
    String? attachedFileName,
    bool useWeb = false,
    String? sessionId,
  }) async {
    final body = <String, dynamic>{
      'query':   queryText,
      'history': history.map((h) => h.toJson()).toList(),
      'use_web': useWeb,
      if (sessionId != null) 'session_id': sessionId,
    };
    if (attachedFileBytes != null && attachedFileName != null) {
      body['attached_file_b64']  = base64Encode(attachedFileBytes);
      body['attached_file_name'] = attachedFileName;
    }
    final res = await _authPost(
      Uri.parse('$baseUrl/query'),
      body: jsonEncode(body),
    );
    if (res.statusCode == 200) return QueryResponse.fromJson(jsonDecode(res.body));
    if (res.statusCode == 401) throw Exception('Session expired — please log in again.');
    if (res.statusCode == 429) throw Exception('Too many requests — please wait a moment.');
    if (res.statusCode == 504) throw Exception('Query timed out — try a simpler question.');
    throw Exception('Query failed (${res.statusCode}): ${_detail(res)}');
  }

  // ── Chat Sessions ────────────────────────────────────────────────────────────

  static Future<List<ChatSession>> listSessions({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/sessions'));
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return (data['sessions'] as List).map((e) => ChatSession.fromJson(e)).toList();
    }
    throw Exception(_detail(res));
  }

  static Future<ChatSession> createSession({
    String userId = '',
    String password = '',
    String title = 'New Chat',
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/sessions'),
      body: jsonEncode({'title': title}),
    );
    if (res.statusCode == 200) return ChatSession.fromJson(jsonDecode(res.body));
    throw Exception(_detail(res));
  }

  static Future<List<Map<String, dynamic>>> getSessionMessages({
    String userId = '',
    String password = '',
    required String sessionId,
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/sessions/$sessionId/messages'));
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return List<Map<String, dynamic>>.from(data['messages'] as List);
    }
    throw Exception(_detail(res));
  }

  static Future<void> deleteSession({
    String userId = '',
    String password = '',
    required String sessionId,
  }) async {
    final res = await _authDelete(Uri.parse('$baseUrl/sessions/$sessionId'));
    if (res.statusCode != 200) throw Exception(_detail(res));
  }

  // ── DB connections (admin) ───────────────────────────────────────────────────
  static Future<Map<String, dynamic>> dbConnections({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/db/connections'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception('Failed to fetch connections: ${res.statusCode}');
  }

  static Future<Map<String, dynamic>> dbConnect({
    String userId = '',
    String password = '',
    required String dbType,
    String? dbPath,
    String? host,
    int? port,
    String? database,
    String? username,
    String? dbPassword,
    String? label,
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/db/connect'),
      body: jsonEncode({
        'db_type': dbType,
        if (dbPath    != null) 'db_path':   dbPath,
        if (host      != null) 'host':       host,
        if (port      != null) 'port':       port,
        if (database  != null) 'database':   database,
        if (username  != null) 'username':   username,
        if (dbPassword != null) 'password':  dbPassword,
        if (label     != null) 'label':      label,
      }),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception('DB connect failed (${res.statusCode}): ${res.body}');
  }

  // ── Audit log ───────────────────────────────────────────────────────────────
  static Future<List<AuditEntry>> auditLog({
    String userId = '',
    String password = '',
    String? filterUid,
    String? eventType,
    int limit = 50,
  }) async {
    final params = <String, String>{
      'limit': limit.toString(),
      if (filterUid != null && filterUid.isNotEmpty) 'filter_uid': filterUid,
      if (eventType != null && eventType.isNotEmpty) 'event_type': eventType,
    };
    final uri = Uri.parse('$baseUrl/audit').replace(queryParameters: params);
    final res = await _authGet(uri);
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body);
      final list = data is List ? data : (data['entries'] ?? data['logs'] ?? []);
      return (list as List).map((e) => AuditEntry.fromJson(e)).toList();
    }
    if (res.statusCode == 403) throw Exception('Admin or manager access required.');
    throw Exception(_detail(res));
  }

  // ── Agent stats ─────────────────────────────────────────────────────────────
  static Future<Map<String, dynamic>> agentStats({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/agents/stats'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    if (res.statusCode == 403) throw Exception('Admin or manager access required.');
    throw Exception(_detail(res));
  }

  // ── LLM configuration (admin) ────────────────────────────────────────────────
  static Future<Map<String, dynamic>> llmConfigure({
    String userId = '',
    String password = '',
    required String provider,
    String? apiKey,
    String? model,
    String? ollamaUrl,
    String? ollamaModel,
  }) async {
    final body = <String, dynamic>{'provider': provider};
    if (apiKey      != null && apiKey.isNotEmpty)      body['api_key']      = apiKey;
    if (model       != null && model.isNotEmpty)       body['model']        = model;
    if (ollamaUrl   != null && ollamaUrl.isNotEmpty)   body['ollama_url']   = ollamaUrl;
    if (ollamaModel != null && ollamaModel.isNotEmpty) body['ollama_model'] = ollamaModel;

    final res = await _authPost(
      Uri.parse('$baseUrl/llm/configure'),
      body: jsonEncode(body),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    if (res.statusCode == 403) throw Exception('Admin access required.');
    throw Exception('LLM configure failed (${res.statusCode}): ${res.body}');
  }

  static Future<List<String>> llmModels({
    String userId = '',
    String password = '',
    required String provider,
    String apiKey = '',
    String ollamaUrl = '',
  }) async {
    final params = <String, String>{
      'provider': provider,
      if (apiKey.isNotEmpty)    'api_key':    apiKey,
      if (ollamaUrl.isNotEmpty) 'ollama_url': ollamaUrl,
    };
    final uri = Uri.parse('$baseUrl/llm/models').replace(queryParameters: params);
    final res = await _authGet(uri);
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return List<String>.from(data['models'] ?? []);
    }
    if (res.statusCode == 403) throw Exception('Admin access required.');
    final detail = jsonDecode(res.body)['detail'] ?? res.body;
    throw Exception('$detail');
  }

  static Future<Map<String, dynamic>> llmStatus({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/llm/status'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception('LLM status failed: ${res.statusCode}');
  }

  // ── Document ingest by server path ──────────────────────────────────────────
  static Future<Map<String, dynamic>> ingest({
    String userId = '',
    String password = '',
    required String filePath,
    required String deptTag,
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/ingest'),
      body: jsonEncode({'file_path': filePath, 'dept_tag': deptTag}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception('Ingest failed (${res.statusCode}): ${res.body}');
  }

  // ── Upload file from browser ─────────────────────────────────────────────────
  static Future<Map<String, dynamic>> uploadFile({
    String userId = '',
    String password = '',
    required String deptTag,
    required String fileName,
    required Uint8List fileBytes,
  }) async {
    final uri = Uri.parse('$baseUrl/upload');
    final request = http.MultipartRequest('POST', uri)
      ..headers.addAll(_bearerHeadersNoJson())
      ..fields['dept_tag'] = deptTag
      ..files.add(http.MultipartFile.fromBytes('file', fileBytes, filename: fileName));

    final streamed = await request.send();
    final res = await http.Response.fromStream(streamed);
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception('Upload failed (${res.statusCode}): ${res.body}');
  }

  // ── User self-service ───────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> changePassword({
    String userId = '',
    required String currentPassword,
    required String newPassword,
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/users/change-password'),
      body: jsonEncode({
        'current_password': currentPassword,
        'new_password':     newPassword,
      }),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> userMeta() async {
    final res = await http.get(Uri.parse('$baseUrl/users/meta'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception('Failed to load user meta');
  }

  static Future<Map<String, dynamic>> myAccess({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/users/my-access'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> toggleDbMode({
    String userId = '',
    String password = '',
    required bool enabled,
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/users/db-mode'),
      body: jsonEncode({'enabled': enabled}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  // ── Admin — all requests ────────────────────────────────────────────────────

  static Future<List<dynamic>> adminRequests({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/users/admin-requests'));
    if (res.statusCode == 200) return (jsonDecode(res.body)['requests'] as List);
    throw Exception(_detail(res));
  }

  static Future<List<dynamic>> allRequests({
    String userId = '',
    String password = '',
    String? stage,
  }) async {
    final params = {if (stage != null) 'stage': stage};
    final uri = Uri.parse('$baseUrl/users/requests').replace(queryParameters: params);
    final res = await _authGet(uri);
    if (res.statusCode == 200) return (jsonDecode(res.body)['requests'] as List);
    throw Exception(_detail(res));
  }

  static Future<int> pendingRequestCount({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/users/requests/pending-count'));
    if (res.statusCode == 200) return jsonDecode(res.body)['count'] as int;
    return 0;
  }

  static Future<Map<String, dynamic>> adminApproveRequest({
    String adminId = '',
    String password = '',
    required String reqId,
    String notes = '',
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/users/requests/$reqId/admin-approve'),
      body: jsonEncode({'notes': notes}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> adminRejectRequest({
    String adminId = '',
    String password = '',
    required String reqId,
    String notes = '',
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/users/requests/$reqId/admin-reject'),
      body: jsonEncode({'notes': notes}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  // ── Dept head actions ───────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> deptRequests({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/users/dept-requests'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> deptApproveRequest({
    String userId = '',
    String password = '',
    required String reqId,
    required String dept,
    List<String> projects = const [],
    String notes = '',
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/users/requests/$reqId/dept-approve'),
      body: jsonEncode({'dept': dept, 'projects': projects, 'notes': notes}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> deptRejectRequest({
    String userId = '',
    String password = '',
    required String reqId,
    required String dept,
    String notes = '',
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/users/requests/$reqId/dept-reject'),
      body: jsonEncode({'dept': dept, 'notes': notes}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  // ── Admin — dept head assignment ────────────────────────────────────────────

  static Future<Map<String, dynamic>> listDeptHeads({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/admin/dept-heads'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> assignDeptHead({
    String adminId = '',
    String password = '',
    required String dept,
    required String targetUserId,
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/admin/dept-heads'),
      body: jsonEncode({'dept': dept, 'user_id': targetUserId}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> removeDeptHead({
    String adminId = '',
    String password = '',
    required String dept,
  }) async {
    final res = await _authDelete(Uri.parse('$baseUrl/admin/dept-heads/$dept'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  // ── Division / C-Suite management (admin) ────────────────────────────────────

  static Future<Map<String, dynamic>> getDivisions({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/admin/divisions'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> setDivisionHead({
    String adminId = '',
    String password = '',
    required String division,
    required String targetUserId,
    String title = '',
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/admin/divisions'),
      body: jsonEncode({
        'division': division,
        'user_id':  targetUserId,
        if (title.isNotEmpty) 'title': title,
      }),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> removeDivisionHead({
    String adminId = '',
    String password = '',
    required String division,
  }) async {
    final res = await _authDelete(Uri.parse('$baseUrl/admin/divisions/$division'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  // ── Division head actions ────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> divisionRequests({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/users/division-requests'));
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> divisionApproveRequest({
    String userId = '',
    String password = '',
    required String reqId,
    required String division,
    String notes = '',
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/users/requests/$reqId/division-approve'),
      body: jsonEncode({'division': division, 'notes': notes}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> divisionRejectRequest({
    String userId = '',
    String password = '',
    required String reqId,
    required String division,
    String notes = '',
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/users/requests/$reqId/division-reject'),
      body: jsonEncode({'division': division, 'notes': notes}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  // ── Portal user list ─────────────────────────────────────────────────────────
  static Future<List<dynamic>> listPortalUsers({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/users/list'));
    if (res.statusCode == 200) return (jsonDecode(res.body)['users'] as List);
    throw Exception(_detail(res));
  }

  // ── OneDrive ─────────────────────────────────────────────────────────────────

  static Future<String> onedriveConnectUrl({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/cloud/onedrive/connect'));
    if (res.statusCode == 200) return jsonDecode(res.body)['auth_url'] as String;
    throw Exception(_detail(res));
  }

  static Future<CloudStatus> onedriveStatus({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/cloud/onedrive/status'));
    if (res.statusCode == 200) return CloudStatus.fromJson(jsonDecode(res.body));
    throw Exception(_detail(res));
  }

  static Future<List<CloudFile>> onedriveFiles({
    String userId = '',
    String password = '',
    String folderPath = '/',
  }) async {
    final uri = Uri.parse('$baseUrl/cloud/onedrive/files')
        .replace(queryParameters: {'folder_path': folderPath});
    final res = await _authGet(uri);
    if (res.statusCode == 200) {
      return (jsonDecode(res.body)['files'] as List).map((e) => CloudFile.fromJson(e)).toList();
    }
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> onedriveImport({
    String userId = '',
    String password = '',
    required String itemId,
    required String deptTag,
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/cloud/onedrive/import'),
      body: jsonEncode({'item_id': itemId, 'dept_tag': deptTag}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<void> onedriveDisconnect({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authDelete(Uri.parse('$baseUrl/cloud/onedrive/disconnect'));
    if (res.statusCode != 200) throw Exception(_detail(res));
  }

  // ── Gmail ─────────────────────────────────────────────────────────────────────

  static Future<String> gmailConnectUrl({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/cloud/gmail/connect'));
    if (res.statusCode == 200) return jsonDecode(res.body)['auth_url'] as String;
    throw Exception(_detail(res));
  }

  static Future<CloudStatus> gmailStatus({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/cloud/gmail/status'));
    if (res.statusCode == 200) return CloudStatus.fromJson(jsonDecode(res.body));
    throw Exception(_detail(res));
  }

  static Future<List<GmailLabel>> gmailLabels({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/cloud/gmail/labels'));
    if (res.statusCode == 200) {
      return (jsonDecode(res.body)['labels'] as List).map((e) => GmailLabel.fromJson(e)).toList();
    }
    throw Exception(_detail(res));
  }

  static Future<List<GmailMessage>> gmailMessages({
    String userId = '',
    String password = '',
    String labelId = 'INBOX',
    int max = 20,
  }) async {
    final uri = Uri.parse('$baseUrl/cloud/gmail/messages')
        .replace(queryParameters: {'label_id': labelId, 'max': '$max'});
    final res = await _authGet(uri);
    if (res.statusCode == 200) {
      return (jsonDecode(res.body)['messages'] as List).map((e) => GmailMessage.fromJson(e)).toList();
    }
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> gmailImportMessage({
    String userId = '',
    String password = '',
    required String messageId,
    required String deptTag,
  }) async {
    final res = await _authPost(
      Uri.parse('$baseUrl/cloud/gmail/import/message'),
      body: jsonEncode({'message_id': messageId, 'dept_tag': deptTag}),
    );
    if (res.statusCode == 200) return jsonDecode(res.body);
    throw Exception(_detail(res));
  }

  static Future<void> gmailDisconnect({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authDelete(Uri.parse('$baseUrl/cloud/gmail/disconnect'));
    if (res.statusCode != 200) throw Exception(_detail(res));
  }

  // ── Department Config ────────────────────────────────────────────────────────

  static Future<List<dynamic>> listDepartments({
    String userId = '',
    String password = '',
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/departments'));
    if (res.statusCode == 200) return jsonDecode(res.body) as List<dynamic>;
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> getDeptRagConfig({
    String userId = '',
    String password = '',
    required String dept,
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/departments/$dept/rag-config'));
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> updateDeptRagConfig({
    String userId = '',
    String password = '',
    required String dept,
    required Map<String, dynamic> updates,
  }) async {
    final res = await _authPut(
      Uri.parse('$baseUrl/departments/$dept/rag-config'),
      body: jsonEncode(updates),
    );
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> getDeptDbConfig({
    String userId = '',
    String password = '',
    required String dept,
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/departments/$dept/db-config'));
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> updateDeptDbConfig({
    String userId = '',
    String password = '',
    required String dept,
    required Map<String, dynamic> updates,
  }) async {
    final res = await _authPut(
      Uri.parse('$baseUrl/departments/$dept/db-config'),
      body: jsonEncode(updates),
    );
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> testDeptDbConnection({
    String userId = '',
    String password = '',
    required String dept,
  }) async {
    final res = await _authPost(Uri.parse('$baseUrl/departments/$dept/db-test'));
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> getDeptRagStats({
    String userId = '',
    String password = '',
    required String dept,
  }) async {
    final res = await _authGet(Uri.parse('$baseUrl/departments/$dept/rag-stats'));
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    throw Exception(_detail(res));
  }

  // ── Backup (admin) ────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> backupConfig() async {
    final res = await _authGet(Uri.parse('$baseUrl/backup/config'));
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> updateBackupConfig(Map<String, dynamic> updates) async {
    final res = await _authPut(
      Uri.parse('$baseUrl/backup/config'),
      body: jsonEncode(updates),
    );
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    throw Exception(_detail(res));
  }

  static Future<Map<String, dynamic>> runBackup({String label = ''}) async {
    final uri = Uri.parse('$baseUrl/backup/run')
        .replace(queryParameters: label.isNotEmpty ? {'label': label} : null);
    final res = await _authPost(uri);
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    throw Exception(_detail(res));
  }

  static Future<List<dynamic>> listBackups() async {
    final res = await _authGet(Uri.parse('$baseUrl/backup/list'));
    if (res.statusCode == 200) return (jsonDecode(res.body)['backups'] as List);
    throw Exception(_detail(res));
  }

  static Future<List<dynamic>> backupProviders() async {
    final res = await _authGet(Uri.parse('$baseUrl/backup/providers'));
    if (res.statusCode == 200) return (jsonDecode(res.body)['providers'] as List);
    throw Exception(_detail(res));
  }

  // ── Helper ──────────────────────────────────────────────────────────────────
  static String _detail(http.Response res) {
    try {
      return jsonDecode(res.body)['detail'] ?? res.body;
    } catch (_) {
      return res.body;
    }
  }
}
