import '../models/user_model.dart';

abstract class AuthLocalDataSource {
  Future<UserModel> login(String username, String password);
}

class AuthLocalDataSourceImpl implements AuthLocalDataSource {
  static const _username = 'admin';
  static const _password = 'admin123';

  @override
  Future<UserModel> login(String username, String password) async {
    await Future.delayed(const Duration(milliseconds: 500));
    if (username == _username && password == _password) {
      return const UserModel(username: _username);
    }
    throw Exception('Invalid credentials');
  }
}
