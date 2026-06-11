import 'package:equatable/equatable.dart';
import '../../domain/entities/candidate.dart';

abstract class CandidatesState extends Equatable {
  const CandidatesState();

  @override
  List<Object?> get props => [];
}

class CandidatesInitial extends CandidatesState {}

class CandidatesLoading extends CandidatesState {}

class CandidatesLoaded extends CandidatesState {
  final List<Candidate> candidates;

  const CandidatesLoaded(this.candidates);

  @override
  List<Object?> get props => [candidates];
}

class CandidatesError extends CandidatesState {
  final String message;

  const CandidatesError(this.message);

  @override
  List<Object?> get props => [message];
}
