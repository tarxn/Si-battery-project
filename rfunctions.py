def get_idx(arr,val):
    flag= True
    a,b=0,0
    for q in range(arr.shape[0]):
        if arr[q]>=val and arr[q]<val+1:
            if flag:
                a=q
                flag=False
            b=q
    return a,b