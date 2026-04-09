class CloudFile {
  final String id;
  final String name;
  final String type; // "file" | "folder"
  final int size;
  final String? mimeType;
  final String? path;

  const CloudFile({
    required this.id,
    required this.name,
    required this.type,
    required this.size,
    this.mimeType,
    this.path,
  });

  bool get isFolder => type == 'folder';

  factory CloudFile.fromJson(Map<String, dynamic> j) => CloudFile(
        id:       j['id'] as String,
        name:     j['name'] as String,
        type:     j['type'] as String? ?? 'file',
        size:     (j['size'] as num?)?.toInt() ?? 0,
        mimeType: j['mime_type'] as String?,
        path:     j['path'] as String?,
      );
}

class CloudStatus {
  final bool connected;
  final String? email;

  const CloudStatus({required this.connected, this.email});

  factory CloudStatus.fromJson(Map<String, dynamic> j) => CloudStatus(
        connected: j['connected'] as bool? ?? false,
        email:     j['email'] as String?,
      );
}

class GmailLabel {
  final String id;
  final String name;
  final String type;

  const GmailLabel({required this.id, required this.name, required this.type});

  factory GmailLabel.fromJson(Map<String, dynamic> j) => GmailLabel(
        id:   j['id'] as String,
        name: j['name'] as String,
        type: j['type'] as String? ?? 'user',
      );
}

class GmailMessage {
  final String id;
  final String subject;
  final String from;
  final String date;
  final String snippet;
  final List<GmailAttachment> attachments;

  const GmailMessage({
    required this.id,
    required this.subject,
    required this.from,
    required this.date,
    required this.snippet,
    this.attachments = const [],
  });

  factory GmailMessage.fromJson(Map<String, dynamic> j) => GmailMessage(
        id:      j['id'] as String,
        subject: j['subject'] as String? ?? '(no subject)',
        from:    j['from'] as String? ?? '',
        date:    j['date'] as String? ?? '',
        snippet: j['snippet'] as String? ?? '',
      );
}

class GmailAttachment {
  final String id;
  final String filename;
  final String mimeType;
  final int size;

  const GmailAttachment({
    required this.id,
    required this.filename,
    required this.mimeType,
    required this.size,
  });

  factory GmailAttachment.fromJson(Map<String, dynamic> j) => GmailAttachment(
        id:       j['id'] as String,
        filename: j['filename'] as String,
        mimeType: j['mime_type'] as String? ?? '',
        size:     (j['size'] as num?)?.toInt() ?? 0,
      );
}
