import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/auth_provider.dart';
import 'providers/chat_provider.dart';
import 'providers/sessions_provider.dart';
import 'providers/cloud_provider.dart';
import 'screens/login_screen.dart';
import 'screens/chat_screen.dart';
import 'screens/audit_screen.dart';
import 'screens/admin_screen.dart';
import 'screens/user_management_screen.dart';
import 'screens/register_screen.dart';
import 'screens/access_profile_screen.dart';
import 'screens/cloud_screen.dart';
import 'theme.dart';

void main() {
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider()),
        ChangeNotifierProvider(create: (_) => ChatProvider()),
        ChangeNotifierProvider(create: (_) => SessionsProvider()),
        ChangeNotifierProvider(create: (_) => CloudProvider()),
      ],
      child: const RapidApp(),
    ),
  );
}

class RapidApp extends StatelessWidget {
  const RapidApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'RAPID',
      theme: rapidTheme,
      debugShowCheckedModeBanner: false,
      initialRoute: '/',
      onGenerateRoute: (settings) {
        final auth = Provider.of<AuthProvider>(
          navigatorKey.currentContext ?? context,
          listen: false,
        );

        switch (settings.name) {
          case '/':
            return MaterialPageRoute(builder: (_) => const LoginScreen());
          case '/register':
            return MaterialPageRoute(builder: (_) => const RegisterScreen());
          case '/chat':
            if (!auth.isLoggedIn) return MaterialPageRoute(builder: (_) => const LoginScreen());
            return MaterialPageRoute(builder: (_) => const ChatScreen());
          case '/access':
            if (!auth.isLoggedIn) return MaterialPageRoute(builder: (_) => const LoginScreen());
            return MaterialPageRoute(builder: (_) => const AccessProfileScreen());
          case '/audit':
            if (!auth.isLoggedIn || !auth.isManager) return MaterialPageRoute(builder: (_) => const LoginScreen());
            return MaterialPageRoute(builder: (_) => const AuditScreen());
          case '/admin':
            if (!auth.isLoggedIn || !auth.isAdmin) return MaterialPageRoute(builder: (_) => const LoginScreen());
            return MaterialPageRoute(builder: (_) => const AdminScreen());
          case '/users':
            if (!auth.isLoggedIn || !auth.isManager) return MaterialPageRoute(builder: (_) => const LoginScreen());
            return MaterialPageRoute(builder: (_) => const UserManagementScreen());
          case '/cloud':
            if (!auth.isLoggedIn) return MaterialPageRoute(builder: (_) => const LoginScreen());
            return MaterialPageRoute(builder: (_) => const CloudScreen());
          default:
            return MaterialPageRoute(builder: (_) => const LoginScreen());
        }
      },
      navigatorKey: navigatorKey,
    );
  }
}

final navigatorKey = GlobalKey<NavigatorState>();
