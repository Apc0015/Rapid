class QueryResponse {
  final String queryId;
  final String answer;
  final double confidence;
  final String? warning;
  final List<String> sources;
  final List<String> deptTags;
  final String actionTaken;

  QueryResponse({
    required this.queryId,
    required this.answer,
    required this.confidence,
    this.warning,
    required this.sources,
    required this.deptTags,
    required this.actionTaken,
  });

  factory QueryResponse.fromJson(Map<String, dynamic> j) => QueryResponse(
    queryId:     j['query_id'] ?? '',
    answer:      j['answer'] ?? '',
    confidence:  (j['confidence'] as num?)?.toDouble() ?? 0.0,
    warning:     j['warning'],
    sources:     List<String>.from(j['sources'] ?? []),
    deptTags:    List<String>.from(j['dept_tags'] ?? []),
    actionTaken: j['action_taken'] ?? '',
  );
}

// Chat message — wraps both user messages and AI responses
class ChatMessage {
  final String text;
  final bool isUser;
  final QueryResponse? response;
  final DateTime timestamp;
  final String? attachedFileName;   // name of attached file if any

  ChatMessage({
    required this.text,
    required this.isUser,
    this.response,
    this.attachedFileName,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();
}

// History entry sent to backend for conversation context
class HistoryMessage {
  final String role;    // "user" | "assistant"
  final String content;
  HistoryMessage({required this.role, required this.content});
  Map<String, dynamic> toJson() => {'role': role, 'content': content};
}
