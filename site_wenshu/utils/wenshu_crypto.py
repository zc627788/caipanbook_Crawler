import base64
import random
import string
from Crypto.Cipher import DES3
from Crypto.Util.Padding import pad, unpad

def generate_random_salt(length=24) -> str:
    """
    对应 $.WebSite.random(24) 生成 24 位随机盐（3DES 密钥）
    """
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))

def encrypt_ciphertext(timestamp_ms: int, salt: str, date_str: str) -> str:
    """
    加密请求参数 ciphertext：
    1. 3DES CBC 加密时间戳，Key为随机盐，IV为当前日期 (yyyymmdd)
    2. 拼接 salt + iv + enc
    3. 将字符串的每个字符转换为二进制表现形式，用空格分隔
    """
    key_bytes = salt.encode('utf-8')
    iv_bytes = date_str.encode('utf-8')
    plaintext_bytes = str(timestamp_ms).encode('utf-8')
    
    # PKCS7 填充
    padded_data = pad(plaintext_bytes, DES3.block_size)
    
    # 3DES CBC 加密
    cipher = DES3.new(key_bytes, DES3.MODE_CBC, iv_bytes)
    encrypted_bytes = cipher.encrypt(padded_data)
    
    # 转为 Base64
    enc = base64.b64encode(encrypted_bytes).decode('utf-8')
    
    # 拼接结果：salt + iv + enc
    final_str = salt + date_str + enc
    
    # 将 final_str 的每个字符转换为二进制形式，并用空格连接
    binary_list = [bin(ord(char))[2:] for char in final_str]
    return " ".join(binary_list)

def decrypt_result(result_b64: str, secret_key: str, date_str: str) -> str:
    """
    解密响应参数 result：
    1. 还原 Markdown 或编辑器转义的 Base64 符号
    2. 使用 3DES CBC 解密，Key为 secretKey，IV为当前日期 (yyyymmdd)
    3. 去除 PKCS7 填充，解码为 UTF-8 字符串
    """
    # 纠正 base64url 格式
    cleaned_b64 = result_b64.replace('_', '/').replace('-', '+').replace(' ', '+')
    cleaned_b64 = cleaned_b64.replace('\n', '').replace('\r', '')
    
    # 剥离任何可能被混入的非法非 base64 字符
    valid_b64_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    cleaned_b64 = "".join([c for c in cleaned_b64 if c in valid_b64_chars])
    
    # 补足 Padding 等号
    missing_padding = len(cleaned_b64) % 4
    if missing_padding:
        cleaned_b64 += '=' * (4 - missing_padding)
        
    ciphertext_bytes = base64.b64decode(cleaned_b64)
    key_bytes = secret_key.encode('utf-8')
    iv_bytes = date_str.encode('utf-8')
    
    # 3DES CBC 解密
    cipher = DES3.new(key_bytes, DES3.MODE_CBC, iv_bytes)
    decrypted_bytes = cipher.decrypt(ciphertext_bytes)
    
    # PKCS7 反填充
    unpadded_bytes = unpad(decrypted_bytes, DES3.block_size)
    return unpadded_bytes.decode('utf-8')
