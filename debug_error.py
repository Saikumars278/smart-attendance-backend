import urllib.request
import urllib.error

try:
    urllib.request.urlopen('http://localhost:8000/leave-approvals/')
except urllib.error.HTTPError as e:
    content = e.read().decode('utf-8')
    with open('error_output.html', 'w', encoding='utf-8') as f:
        f.write(content)
    import re
    m = re.search(r'<title>(.*?)</title>', content)
    print('Title:', m.group(1) if m else 'None')
    m2 = re.search(r'Exception Value:(.*?)</pre>', content, re.S)
    print('Exception:', m2.group(1).strip() if m2 else 'None')
