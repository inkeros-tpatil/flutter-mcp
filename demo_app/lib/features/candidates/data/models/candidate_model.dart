import '../../domain/entities/candidate.dart';

class CandidateModel extends Candidate {
  const CandidateModel({
    required super.id,
    required super.name,
    required super.role,
    required super.email,
    required super.phone,
    required super.location,
    required super.experience,
    required super.skills,
    required super.education,
    required super.summary,
  });
}
