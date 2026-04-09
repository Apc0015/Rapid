class AuditEntry {
  final String queryId;
  final String userId;
  final String rawQuery;
  final String timestamp;
  final String intentClass;
  final List<String> deptsActivated;
  final double? compositeConfidence;
  final String actionTaken;
  final String? eventType;

  AuditEntry({
    required this.queryId,
    required this.userId,
    required this.rawQuery,
    required this.timestamp,
    required this.intentClass,
    required this.deptsActivated,
    this.compositeConfidence,
    required this.actionTaken,
    this.eventType,
  });

  factory AuditEntry.fromJson(Map<String, dynamic> j) => AuditEntry(
    queryId:    j['query_id'] ?? '',
    userId:     j['user_id'] ?? '',
    rawQuery:   j['raw_query'] ?? j['message'] ?? '',
    timestamp:  j['timestamp'] ?? '',
    intentClass: j['intent_class'] ?? '',
    deptsActivated: List<String>.from(j['depts_activated'] ?? []),
    compositeConfidence: (j['composite_confidence'] as num?)?.toDouble(),
    actionTaken: j['action_taken'] ?? '',
    eventType:   j['event_type'],
  );
}
