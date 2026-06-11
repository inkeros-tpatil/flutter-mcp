import 'package:equatable/equatable.dart';

abstract class CandidatesEvent extends Equatable {
  const CandidatesEvent();

  @override
  List<Object?> get props => [];
}

class LoadCandidates extends CandidatesEvent {}
