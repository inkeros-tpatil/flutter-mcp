import 'package:equatable/equatable.dart';

class Candidate extends Equatable {
  final int id;
  final String name;
  final String role;
  final String email;
  final String phone;
  final String location;
  final int experience;
  final List<String> skills;
  final String education;
  final String summary;

  const Candidate({
    required this.id,
    required this.name,
    required this.role,
    required this.email,
    required this.phone,
    required this.location,
    required this.experience,
    required this.skills,
    required this.education,
    required this.summary,
  });

  @override
  List<Object?> get props => [id];
}
