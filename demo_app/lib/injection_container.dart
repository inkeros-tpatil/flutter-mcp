import 'package:get_it/get_it.dart';
import 'features/auth/data/datasources/auth_local_datasource.dart';
import 'features/auth/data/repositories/auth_repository_impl.dart';
import 'features/auth/domain/repositories/auth_repository.dart';
import 'features/auth/domain/usecases/login_usecase.dart';
import 'features/auth/presentation/bloc/auth_bloc.dart';
import 'features/candidates/data/datasources/candidates_local_datasource.dart';
import 'features/candidates/data/repositories/candidates_repository_impl.dart';
import 'features/candidates/domain/repositories/candidates_repository.dart';
import 'features/candidates/domain/usecases/get_candidates_usecase.dart';
import 'features/candidates/presentation/bloc/candidates_bloc.dart';

final sl = GetIt.instance;

void initDependencies() {
  // Data sources
  sl.registerLazySingleton<AuthLocalDataSource>(
    () => AuthLocalDataSourceImpl(),
  );
  sl.registerLazySingleton<CandidatesLocalDataSource>(
    () => CandidatesLocalDataSourceImpl(),
  );

  // Repositories
  sl.registerLazySingleton<AuthRepository>(
    () => AuthRepositoryImpl(sl()),
  );
  sl.registerLazySingleton<CandidatesRepository>(
    () => CandidatesRepositoryImpl(sl()),
  );

  // Use cases
  sl.registerLazySingleton(() => LoginUseCase(sl()));
  sl.registerLazySingleton(() => GetCandidatesUseCase(sl()));

  // BLoCs
  sl.registerFactory(() => AuthBloc(sl()));
  sl.registerFactory(() => CandidatesBloc(sl()));
}
