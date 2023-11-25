import re
import requests
import csv
import queue
from tqdm import tqdm

HEADERS = ["bid","name","full_class","class3"]

base_url = "https://www.librarything.com/mds/{number}"
new_shelf_url = "https://www.librarything.com/ajaxinc_newshelf.php"
book_url = "https://www.librarything.com/work/{bid}"

cookies = {
    "cookie_from":"https%3A%2F%2Fwww.google.com%2F",
    "LTAnonSessionID":"417091460",
    "__utmv":"156890278.LTNonMember",
    "__utmc":"156890278",
    "__utmz":"156890278.1686993341.2.2.utmcsr=google|utmccn=(organic)|utmcmd=organic|utmctr=(not%20provided)",
    "gdpr_notice_clicked":"1",
    "__utma":"156890278.623089323.1685026591.1686993341.1687358613.3",
    "_ga":"GA1.1.1833875588.1689008270",
    "LTUnifiedCookie":"%7B%22areyouhuman%22%3A1%7D",
    "_ga_3FXSBC8C5V":"GS1.1.1689366148.5.1.1689367623.0.0.0"
}
next_shelf_payload = {
    "listtype": "ddc",
    "cachekey": "u_5e15be19",
    "displaymode": 0,
    "shelfoffset": 6, #STARTS 0 JUMPS 6
    "numoffset": 50, #STARTS 0 JUMPS 50
    "sort": 4,
    "orderby": 0,
    "xhr": "true",
    "width": 973, #DISPALY WIDTH, NOT RELEVANT
    "prettify_selector": "#ddc",
    "forceLT2": 1,
    "is_ajax": 1
}

book_pattern = r"<div class=\"lt2_columnar_item\"><li><a href=\"/work/\d+\" data-workid=\"(?P<id>\d+)\" data-title=\".*?\" class=\"\">(?P<name>.*?)</a>"
successor_pattern = r"<td class=\"ddcl\d\"  onclick=\"classification_link\('ddc', '(?P<class>[\d\.]+)'\);"
cache_pattern = r"<a href=\"javascript:loadNewShelf\('ddc','(?P<cachekey>u_[0-9a-f]{8})',0,(?P<shelfoffset>\d+),(?P<numoffset>\d+),\d+,'0',0,\);\">\s*next <i class=\"fas fa-chevron-right\"></i>\s*</a>"
reg_description_pattern = r"<tr class=\"wslcontent wslsummary\">\s*<td colspan=\"7\" class=\"lastchild\">\s*<div class=\"\">(?P<description>.*?)</div class=\"\">\s*</td>\s*</tr>"
show_more_description_pattern = r"<tr class=\"wslcontent wslsummary\">\s*<td colspan=\"\d\" class=\"lastchild\">\s*<div class=\"showmore\" id=\"u_[0-9a-f]{8}\">\s*(?P<description1>.*?)<u class=\"showmore_hide\">(?P<description2>.*?)</u>\s*<span class=\"showmore_showlink\">"

def scrape_books_for_shelf(text, num):
    """
    accepts text of requests and rerturns a dict of books in it
    """
    # extract the book name and add modifications
    books = re.findall(pattern=book_pattern, string=text)
    num3 = num[0:3]
    books = {bid: (name, num, num3) for bid, name in books}
    return books

def iterate_all_shelfs_for_num(text, num):
    """
    accepts text of base requests and iterates all the continuations if exists.
    """
    books = scrape_books_for_shelf(text, num)

    state_id = re.findall(pattern=cache_pattern, string=text)
    state_id = state_id[0] if state_id else None
    while state_id:
        # getting POST request of the next shelf
        payload_update = dict(zip(["cachekey", "shelfoffset", "numoffset"], list(state_id)))
        next_shelf_payload.update(payload_update)
        r = requests.post(new_shelf_url, data=next_shelf_payload)

        # extracting from next shelf the books
        new_text = r.text
        new_books = scrape_books_for_shelf(new_text, num)
        books.update(new_books)

        # loop continuation - finding again the next shelf
        state_id = re.findall(pattern=cache_pattern, string=new_text)
        state_id = state_id[0] if state_id else None

    return books

def find_successors(text, root):
    # successor numbers in DDC
    if len(root) == 3:
        root += "."
    optional_successors = []
    for i in range(0, 10):
        optional_successors.append(root[::]+str(i))

    # scraping from the HTML page which successors are not empty pages
    relevant_successors = re.findall(pattern=successor_pattern, string=text)

    # intersection between both is the successors I need
    return [value for value in optional_successors if value in relevant_successors]


def bfs_tree_scraping_for_number_inclusive(root, scrape_descriptions=False):
    """
    scrapes the given number and all of its successors
    :param root:
    :return: books dict
    """
    numbers_queue = queue.Queue()
    numbers_queue.put(root)
    books = {}
    while not numbers_queue.empty():
        num = numbers_queue.get()
        print(num)

        # Query the URL
        r = requests.get(base_url.format(number=num), cookies=cookies)
        if r.status_code != 200:
            print("error")

        # BFS Continuation
        successors = find_successors(r.text, num)
        for succ in successors:
            numbers_queue.put(succ)

        if len(num) >= 3:
            books_for_num = iterate_all_shelfs_for_num(r.text, num)
            books.update(books_for_num)

    if scrape_descriptions:
        print("Loading Descriptions...")
        books_with_descriptions = []
        for bid, values in tqdm(books.items()):
            name, num, num3 = values
            desc = extract_description(bid)
            books_with_descriptions.append((bid, num, name, desc))
        return books_with_descriptions
    else:
        return [[bid]+list(features) for bid, features in books.items()]

def extract_description(bid):
    text = requests.get(book_url.format(bid=bid)).text
    des = re.findall(pattern=reg_description_pattern, string=text)
    if des:
        return des[0]
    des = re.findall(pattern=show_more_description_pattern, string=text)
    if des:
        return des[0][0]+des[0][1]
    return None

def scrape_to_file(root, path):
    books = bfs_tree_scraping_for_number_inclusive(root)

    with open(path, "w", encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=",", lineterminator="\n")
        writer.writerow(HEADERS)
        writer.writerows(books)

def main():
    ### MISSING: 15, 20-39, 42
    for i in range(20, 30):
        try:
            scrape_to_file(str(i), "{f}-books.csv".format(f=str(i)))
            print("{f} Completed".format(f=str(i)))
        except Exception as e:
            print("{f} NOT PRINTED".format(f=i))
            print(e)


if __name__ == '__main__':
    main()
