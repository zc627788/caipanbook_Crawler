重头来过，我清除所有内容，重新登录，设计到得接口你给你
刷新阶段
1.
fetch("https://wenshu.court.gov.cn/tongyiLogin/authorize", {
  "headers": {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest"
  },
  "referrer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login",
  "body": null,
  "method": "POST",
  "mode": "cors",
  "credentials": "omit"
});
response：https://account.court.gov.cn/oauth/authorize?response_type=code&client_id=zgcpwsw&redirect_uri=https%3A%2F%2Fwenshu.court.gov.cn%2FCallBackController%2FauthorizeCallBack&state=388558ae-5db7-4f69-a58b-99e572d7bfbe&timestamp=1783502321288&signature=6C23CBFDB6EE0060EC4322F08661FB07779269F880028A39F3F45AC84849B512&scope=userinfo


拿验证码
fetch("https://account.court.gov.cn/captcha/getBase64?appDomain=wenshu.court.gov.cn", {
  "headers": {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest"
  },
  "referrer": "https://account.court.gov.cn/app",
  "body": null,
  "method": "GET",
  "mode": "cors",
  "credentials": "include"
});

3.
fetch("https://account.court.gov.cn/api/third/alipay/mini/getAlipayAppletQrCode", {
  "headers": {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest"
  },
  "referrer": "https://account.court.gov.cn/app",
  "body": "appId=2019110468943166&url=pages%2FgetPhoneNumber%2FgetPhoneNumber&queryParams=appId%3D2019110468943166&type=reg&appDomain=wenshu.court.gov.cn",
  "method": "POST",
  "mode": "cors",
  "credentials": "include"
});
resposne：{
    "url": "https://mass.alipay.com/wsdk/img?fileid=A*UQpLRoXCqW0AAAAAAAAAAAAAAQAAAQ&bz=am_afts_openhome&zoom=227w_277h",
    "uuid": "83d226f794044bfb9886a5f80b335e3b_0"
}

fetch("https://arms-retcode.aliyuncs.com/r.png?t=pv&times=1&page=scan&tag=&release=onlineCourt%2Faccount%2F1.0.120&environment=prod&begin=1783502322151&uid=mFmLtr646tRhea06wi963Fw8nnqC&dt=%E7%BB%9F%E4%B8%80%E8%B4%A6%E5%8F%B7%E4%B8%AD%E5%BF%83&dr=https%3A%2F%2Fwenshu.court.gov.cn%2F&dpr=1.25&de=utf-8&ul=zh-CN&sr=1536x960&vp=0x0&ct=4g&sid=s1m3RrUabI3gs7k13rwU3m0np0Cp&pid=clmcc3gj93%4025ded61374ba2af&_v=1.8.31&pv_id=3Lmqer18bzOvXR87gesOvdzwstv1&sampling=1&dl=https%3A%2F%2Faccount.court.gov.cn%2Fapp%23%2Fscan&z=mrbv8eu8", {
  "headers": {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-site": "cross-site"
  },
  "referrer": "https://account.court.gov.cn/",
  "body": null,
  "method": "HEAD",
  "mode": "cors",
  "credentials": "omit"
});
fetch("https://arms-retcode.aliyuncs.com/r.png?t=pv&times=1&page=scan&tag=&release=onlineCourt%2Faccount%2F1.0.120&environment=prod&begin=1783502322231&uid=mFmLtr646tRhea06wi963Fw8nnqC&dt=%E7%BB%9F%E4%B8%80%E8%B4%A6%E5%8F%B7%E4%B8%AD%E5%BF%83&dr=https%3A%2F%2Fwenshu.court.gov.cn%2F&dpr=1.25&de=utf-8&ul=zh-CN&sr=1536x960&vp=0x0&ct=4g&sid=s1m3RrUabI3gs7k13rwU3m0np0Cp&pid=clmcc3gj93%4025ded61374ba2af&_v=1.8.31&pv_id=3Lmqer18bzOvXR87gesOvdzwstv1&sampling=1&dl=https%3A%2F%2Faccount.court.gov.cn%2Fapp%23%2Fscan&z=mrbv8eu9", {
  "headers": {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-site": "cross-site"
  },
  "referrer": "https://account.court.gov.cn/",
  "body": null,
  "method": "HEAD",
  "mode": "cors",
  "credentials": "omit"
});
fetch("https://account.court.gov.cn/api/third/alipay/pc/pollPhone?uuid=83d226f794044bfb9886a5f80b335e3b_0&appDomain=wenshu.court.gov.cn", {
  "headers": {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest"
  },
  "referrer": "https://account.court.gov.cn/app",
  "body": null,
  "method": "GET",
  "mode": "cors",
  "credentials": "include"
});
response：{
    "code": "000000",
    "data": {
        "code": "0",
        "mobile": null,
        "token": null
    },
    "message": "成功",
    "success": true
}

这个时候我发现就存储了SESSION e0d71936-ae22-48fd-9645-50d57280afbd

开始登录

fetch("https://account.court.gov.cn/captcha/validate", {
  "headers": {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest"
  },
  "referrer": "https://account.court.gov.cn/app?back_url=https%3A%2F%2Faccount.court.gov.cn%2Foauth%2Fauthorize%3Fresponse_type%3Dcode%26client_id%3Dzgcpwsw%26redirect_uri%3Dhttps%253A%252F%252Fwenshu.court.gov.cn%252FCallBackController%252FauthorizeCallBack%26state%3D388558ae-5db7-4f69-a58b-99e572d7bfbe%26timestamp%3D1783502321288%26signature%3D6C23CBFDB6EE0060EC4322F08661FB07779269F880028A39F3F45AC84849B512%26scope%3Duserinfo",
  "body": "appkey=akan&answer=d3Mf&token=0b561cf9328372caa30ec2d23589509ae1756934404b3ef1ef48ef6d9d5c1e33eb43397c0f0103e33e2a202a147c81b70f59147079d14c41a6b628d5f24204faad31e353c98455dfa86db90fdb4fc310ef4233081ee7ca7367c3eb9536c3608869e86f33ecfb3e145016e4cb420d2af90e9b493c24065fd6699dbe7f56c6c16babd38e9ed42bc0dffcbe8ae634bdb6ad800d0484b064c0b423c3c5907c207974&sessionId=016286d9-3a70-475f-b199-2fd50ca282c3&appDomain=wenshu.court.gov.cn",
  "method": "POST",
  "mode": "cors",
  "credentials": "include"
});
response 
{
    "code": 0,
    "data": {
        "code": 0,
        "message": "SUCCESS",
        "cert": "53703ef1a5dbce66dae8a65e9e79736f9019cedb5bcfa165a731ee2548b3349455cf940f652f12b5abecaf79ace5c7764bbc7bc25dd6d4a9b91edfc8f532c542c903e756757f4188fdd79907ce0fc2262b9ed59006d4505857d465cdba7bb89c1ed27962742b89c90d927358934d528895ada4dbf348d75e7712667b7c7a5da499fd9c1cda693a48493c747b430aa33629077ab04ee318a4cb8e24510eecc5cc"
    },
    "message": "SUCCESS",
    "success": true
}

{
    "code": 0,
    "data": {
        "code": 0,
        "message": "SUCCESS",
        "cert": "53703ef1a5dbce66dae8a65e9e79736f9019cedb5bcfa165a731ee2548b3349455cf940f652f12b5abecaf79ace5c7764bbc7bc25dd6d4a9b91edfc8f532c542c903e756757f4188fdd79907ce0fc2262b9ed59006d4505857d465cdba7bb89c1ed27962742b89c90d927358934d528895ada4dbf348d75e7712667b7c7a5da499fd9c1cda693a48493c747b430aa33629077ab04ee318a4cb8e24510eecc5cc"
    },
    "message": "SUCCESS",
    "success": true
}
一直轮询

fetch("https://account.court.gov.cn/api/login", {
  "headers": {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest"
  },
  "referrer": "https://account.court.gov.cn/app?back_url=https%3A%2F%2Faccount.court.gov.cn%2Foauth%2Fauthorize%3Fresponse_type%3Dcode%26client_id%3Dzgcpwsw%26redirect_uri%3Dhttps%253A%252F%252Fwenshu.court.gov.cn%252FCallBackController%252FauthorizeCallBack%26state%3D388558ae-5db7-4f69-a58b-99e572d7bfbe%26timestamp%3D1783502321288%26signature%3D6C23CBFDB6EE0060EC4322F08661FB07779269F880028A39F3F45AC84849B512%26scope%3Duserinfo",
  "body": "username=63-9568348610&password=JvrC%252BRXaEyVhOBhiaadPU2gP95lHlXjKEp8YUjh6cIz3f0oxUGmBEwE0FHIturp9S43V4w0Be1tx1ulM4yA9oKo%252FzR4Z2nTX2%252BkXdkRBhVnVHFG1B6I71jxtmRPYJ7qYQJYgbWVlAecgaEwfW%252BzZHgnSuxq5BOGQKXH%252BJB5Q%252FOC0kH2nyyP8%252BU6DpjYRsmQKG9WgmbhHTUOyO9da9aZM%252FP471onrWv15lFziiKkx%252F4L%252FVXwR6oqH1Nbz7bn0wVa6Feo1bcxoQTlIus15MKIdD8pX8WmXB7PPS%252FAW6K05GPuh6CY1PZWBXIFB100AgOOARPkOgofn1AMvZoKpDX%252BNYg%253D%253D&bizToken=016286d9-3a70-475f-b199-2fd50ca282c3&imgVerifyToken=016286d9-3a70-475f-b199-2fd50ca282c3&appDomain=wenshu.court.gov.cn",
  "method": "POST",
  "mode": "cors",
  "credentials": "include"
});
这是login response cookie是这个e
HOLDONKEY MjYxNzdkODAtNWFlZi00ZDg0LWI1M2MtOWNlOTFhMjc0NjE2

其他request
_bl_uid	mFmLtr646tRhea06wi963Fw8nnqC	account.court.gov.cn	/	2026-12-31T14:41:47.156Z	35						Medium
CNZZDATA1280020211	2074276631-1783434765-%7C1783434765	
www.court.gov.cn	/	2027-01-05T14:32:45.000Z	53						Medium
HOLDONKEY	YWNlNzNlZTMtODc0YS00Nzc1LThjZDQtZTJlMjFkYTQxMTlj	account.court.gov.cn	/	Session	57	✓	✓	None			Medium
ncCookie	_Uuh-6PV0WiGDfp3o-2whxESGouT7YkPpDNHbDGOKoAxdrMthWB_MgHZSFIivi_SslkhhfyXOd-pGGoriiBcrOnbbH6D0BFVejigivPzLhfKLBl--1gdiKWe5E_ooHMl	account.court.gov.cn	/	2027-07-08T09:22:30.744Z	136	✓	✓	None			Medium
SESSION	e0d71936-ae22-48fd-9645-50d57280afbd	
wenshu.court.gov.cn	/	Session	43	✓		

开着f12 response 没有内容
关闭以后，首页账号信息出现，可能有什么拦截了
这就是完整过程

账号和密码
# 真实明文账号密码
USERNAME = "63-9568348610"
# 真实明文密码
PASSWORD = "Zc627788***"