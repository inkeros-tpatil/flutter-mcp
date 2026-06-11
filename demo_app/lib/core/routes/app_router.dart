import 'package:flutter/material.dart';
import '../../features/auth/presentation/pages/login_page.dart';
import '../../features/candidates/domain/entities/candidate.dart';
import '../../features/candidates/presentation/pages/home_page.dart';
import '../../features/candidates/presentation/pages/candidate_detail_page.dart';

class AppRouter {
  static const String login = '/';
  static const String home = '/home';
  static const String candidateDetail = '/candidate-detail';

  static Route<dynamic> generateRoute(RouteSettings settings) {
    switch (settings.name) {
      case login:
        return MaterialPageRoute(builder: (_) => const LoginPage());
      case home:
        return MaterialPageRoute(builder: (_) => const HomePage());
      case candidateDetail:
        final candidate = settings.arguments as Candidate;
        return MaterialPageRoute(
          builder: (_) => CandidateDetailPage(candidate: candidate),
        );
      default:
        return MaterialPageRoute(
          builder: (_) => const Scaffold(
            body: Center(child: Text('Page not found')),
          ),
        );
    }
  }
}
